"""Chat API - 主对话端点"""
from __future__ import annotations

import re

from loguru import logger
from pydantic import BaseModel, Field
from fastapi import APIRouter

from core.i18n import t, get_locale, set_locale
from core.stream import sse_response

# session_id 格式：UUID-v4 变体 + base36 时间戳后缀（含 a-z）
_SESSION_ID_RE = re.compile(r"^[0-9a-z\-]{15,50}$")

router = APIRouter()

def get_opening_config():
    return {
        "agent_name": t("opening.agent_name"),
        "agent_avatar": "🍽️",
        "agent_intro": t("opening.agent_intro"),
        "suggested_questions": [
            t("opening.q1"),
            t("opening.q2"),
            t("opening.q3"),
            t("opening.q4"),
        ],
    }


@router.get("/opening")
async def chat_opening():
    """获取开场白配置"""
    return {"success": True, "data": get_opening_config()}


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=10000)
    session_id: str | None = None


class ChatSyncResponse(BaseModel):
    success: bool
    data: dict | None = None
    error: str | None = None
    suggestion: str | None = None


@router.post("")
async def chat_stream(req: ChatRequest):
    """SSE 流式对话"""
    from main import orchestrator

    if not orchestrator:
        return {"success": False, "error": "Orchestrator not initialized"}

    locale = get_locale()

    async def locale_aware_stream():
        set_locale(locale)
        async for event in orchestrator.run_stream(req.message, req.session_id):
            yield event

    return sse_response(locale_aware_stream())


class UserInputRequest(BaseModel):
    request_id: str = Field(..., pattern=r"^[0-9a-f]{10}$")
    value: str = Field(..., max_length=2000)


@router.post("/input")
async def chat_user_input(req: UserInputRequest):
    """接收用户内联输入，唤醒等待中的工具"""
    from core.interfaces.tool import resolve_user_input

    if resolve_user_input(req.request_id, req.value):
        return {"success": True}
    return {"success": False, "error": "请求已过期或不存在"}


@router.get("/history")
async def chat_history(session_id: str, limit: int = 50, offset: int = 0):
    """获取会话历史（支持分页）"""
    if not _SESSION_ID_RE.match(session_id):
        return {"success": False, "error": "无效的 session_id", "data": [], "total": 0}
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    from main import registry

    memory = registry.get_memory("short_term_memory")
    if not memory:
        return {"success": True, "data": [], "total": 0}

    try:
        # 直接查 PG 获取精确分页
        from core.database import get_session_factory, ChatMessage
        from sqlalchemy import select, func

        factory = get_session_factory()
        async with factory() as session:
            # 总数
            count_stmt = select(func.count()).where(ChatMessage.session_id == session_id)
            total = (await session.execute(count_stmt)).scalar() or 0

            # 分页查询（最新的在后面）
            stmt = (
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.id)
                .offset(offset)
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

        turns = []
        for r in rows:
            turn: dict = {"id": r.id, "role": r.role, "content": r.content}
            if r.created_at:
                turn["created_at"] = r.created_at.isoformat()
            if r.tool_data:
                import json as _json
                try:
                    turn["tool_calls"] = _json.loads(r.tool_data)
                except Exception:
                    pass
            turns.append(turn)
        return {"success": True, "data": turns, "total": total}
    except Exception as e:
        logger.error(f"获取聊天历史失败: {e}")
        # 回落到 memory 接口
        try:
            items = await memory.retrieve(session_id, top_k=limit)
            turns = [item.value for item in items if isinstance(item.value, dict)]
            return {"success": True, "data": turns, "total": len(turns)}
        except Exception as e2:
            logger.error(f"回落 memory 接口也失败: {e2}")
            return {"success": False, "error": "获取聊天历史失败", "data": [], "total": 0}


@router.delete("/history")
async def chat_clear(session_id: str):
    """清除指定会话的聊天记录（PG + Redis）"""
    if not _SESSION_ID_RE.match(session_id):
        return {"success": False, "error": "无效的 session_id"}

    from core.database import get_session_factory, ChatMessage
    from sqlalchemy import delete

    try:
        # 1. 清 PostgreSQL
        factory = get_session_factory()
        async with factory() as session:
            stmt = delete(ChatMessage).where(ChatMessage.session_id == session_id)
            result = await session.execute(stmt)
            await session.commit()

        # 2. 清 Redis 缓存
        from main import registry
        memory = registry.get_memory("short_term_memory")
        if memory and hasattr(memory, "_redis") and memory._redis:
            try:
                memory._redis.delete(memory._redis_key(session_id))
            except Exception:
                pass

        return {"success": True, "deleted": result.rowcount}
    except Exception as e:
        logger.error(f"清除历史记录失败: {e}")
        return {"success": False, "error": "清除历史记录失败"}


class UpdateToolDataRequest(BaseModel):
    tool_data: list = Field(..., description="更新后的 tool_calls JSON 数组")


@router.patch("/message/{message_id}")
async def update_message_tool_data(message_id: int, req: UpdateToolDataRequest):
    """更新消息的 tool_data（如采购清单勾选状态）"""
    import json as _json
    from core.database import get_session_factory, ChatMessage

    try:
        factory = get_session_factory()
        async with factory() as session:
            from sqlalchemy import select
            stmt = select(ChatMessage).where(ChatMessage.id == message_id)
            result = await session.execute(stmt)
            msg = result.scalar_one_or_none()
            if not msg:
                return {"success": False, "error": "消息不存在"}
            msg.tool_data = _json.dumps(req.tool_data, ensure_ascii=False)
            await session.commit()
        return {"success": True}
    except Exception as e:
        logger.error(f"更新消息 tool_data 失败: {e}")
        return {"success": False, "error": "更新失败"}


@router.post("/sync")
async def chat_sync(req: ChatRequest) -> ChatSyncResponse:
    """同步对话（等待完整结果）"""
    from main import orchestrator

    if not orchestrator:
        return ChatSyncResponse(success=False, error="Orchestrator not initialized")

    try:
        result = await orchestrator.run_sync(req.message, req.session_id)
        return ChatSyncResponse(success=True, data=result.model_dump())
    except Exception as e:
        logger.error(f"同步对话失败: {e}")
        return ChatSyncResponse(
            success=False,
            error="对话处理失败，请稍后重试",
            suggestion="请检查 LLM provider 配置",
        )
