"""Orchestrator - 编排流水线"""
from __future__ import annotations

import uuid
from typing import Any, AsyncIterator

from loguru import logger

from core.i18n import t
from core.context_bus import ContextBus
from core.intent_router import IntentRouter
from core.interfaces.agent import SSEEvent, AgentResult
from core.interfaces.memory import BaseMemory
from core.models.task import Task
from core.plugin_registry import PluginRegistry
from core.task_decomposer import TaskDecomposer


class Orchestrator:
    """核心编排引擎：Intent → Decompose → Agent → Result"""

    def __init__(
        self,
        registry: PluginRegistry,
        intent_router: IntentRouter,
        task_decomposer: TaskDecomposer,
        memory: BaseMemory | None = None,
    ) -> None:
        self._registry = registry
        self._router = intent_router
        self._decomposer = task_decomposer
        self._memory = memory
        self._comm_manager: Any = None

    def set_comm_manager(self, comm_manager: Any) -> None:
        """设置通信管理器以转发 delegate 事件"""
        self._comm_manager = comm_manager

    async def _load_history(self, session_id: str) -> list[dict]:
        """从 ShortTermMemory 加载对话历史"""
        if not self._memory:
            return []
        try:
            items = await self._memory.retrieve(session_id, top_k=20)
            return [item.value for item in items if isinstance(item.value, dict)]
        except Exception as e:
            logger.warning(f"Failed to load history: {e}")
            return []

    async def _store_turn(
        self, session_id: str, role: str, content: str,
        tool_calls: list[dict] | None = None,
    ) -> int | None:
        """存储一轮对话到 ShortTermMemory，返回数据库记录 id"""
        if not self._memory or (not content.strip() and not tool_calls):
            return None
        try:
            value: dict = {"role": role, "content": content}
            if tool_calls:
                value["tool_calls"] = tool_calls
            return await self._memory.store(session_id, value)
        except Exception as e:
            logger.warning(f"Failed to store turn: {e}")
            return None

    async def run_stream(
        self,
        user_message: str,
        session_id: str | None = None,
    ) -> AsyncIterator[SSEEvent]:
        """流式执行：返回 SSE 事件流"""
        session_id = session_id or str(uuid.uuid4())
        context_bus = ContextBus()

        # 0. 存储用户消息
        await self._store_turn(session_id, "user", user_message)

        # 1. 加载对话历史（不含本轮用户消息，agent.run 会自行追加）
        history = await self._load_history(session_id)
        # 去掉最后一条（就是刚存的当前用户消息）
        if history and history[-1].get("role") == "user" and history[-1].get("content") == user_message:
            history = history[:-1]

        # 2. 意图路由
        intent = await self._router.route(user_message)
        logger.info(f"Intent routed: agent={intent.agent}, confidence={intent.confidence}")

        if intent.confidence < 0.6 or not intent.agent:
            agents = self._registry.list_plugins(plugin_type="agent")
            available = ", ".join(a.name for a in agents) if agents else t("orchestrator.none")
            yield SSEEvent(
                event="error",
                data={
                    "error": t("orchestrator.error.no_match"),
                    "suggestion": t("orchestrator.error.available_agents", available=available),
                },
            )
            return

        # 3. 任务分解
        sub_tasks = await self._decomposer.decompose(intent)

        # 4. 设置 Agent 通信 SSE 回调
        sse_events_buffer: list[SSEEvent] = []
        if self._comm_manager:
            def on_comm_event(event_type: str, data: dict):
                sse_events_buffer.append(SSEEvent(event=event_type, data=data))
            self._comm_manager.set_sse_callback(on_comm_event)

        # 5. 执行 Agent，收集助手回复
        collected_content = ""
        collected_tools: list[dict] = []
        current_tool: dict | None = None

        for sub_task in sub_tasks:
            agent = self._registry.get_agent(sub_task.agent)
            if not agent:
                yield SSEEvent(
                    event="error",
                    data={"error": t("orchestrator.error.agent_not_found", agent=sub_task.agent)},
                )
                return

            agent.context_bus = context_bus

            async for event in agent.run(
                sub_task.description,
                session_id,
                conversation_history=history,
            ):
                # flush 委派事件
                while sse_events_buffer:
                    yield sse_events_buffer.pop(0)

                if event.event == "text_delta":
                    collected_content += event.data.get("content", "")
                elif event.event == "tool_call":
                    current_tool = {
                        "tool": event.data.get("tool", ""),
                        "tool_call_id": event.data.get("tool_call_id", ""),
                        "params": event.data.get("params", {}),
                    }
                elif event.event == "tool_output_done" and current_tool:
                    current_tool["result"] = event.data.get("result")
                    collected_tools.append(current_tool)
                    current_tool = None
                elif event.event == "tool_error" and current_tool:
                    current_tool["result"] = {
                        "success": False, "data": None,
                        "error": event.data.get("error", ""),
                    }
                    collected_tools.append(current_tool)
                    current_tool = None
                yield event

        # 6. 存储助手回复（含工具调用数据），获取数据库 id
        db_id = await self._store_turn(
            session_id, "assistant", collected_content,
            tool_calls=collected_tools or None,
        )

        # 7. 推送消息 id，供前端后续更新（如勾选状态持久化）
        if db_id is not None:
            yield SSEEvent(event="message_saved", data={"message_id": db_id})

    async def run_sync(
        self,
        user_message: str,
        session_id: str | None = None,
    ) -> AgentResult:
        """同步执行：收集所有事件返回结果"""
        session_id = session_id or str(uuid.uuid4())
        collected = {"content": "", "tool_results": [], "agent": ""}

        async for event in self.run_stream(user_message, session_id):
            if event.event == "text_delta":
                collected["content"] += event.data.get("content", "")
            elif event.event == "tool_output_done":
                collected["tool_results"].append(event.data)
            elif event.event == "done":
                collected["agent"] = event.data.get("agent", "")
            elif event.event == "error":
                return AgentResult(
                    session_id=session_id,
                    agent=collected.get("agent", "unknown"),
                    result=event.data,
                )

        return AgentResult(
            session_id=session_id,
            agent=collected["agent"],
            result={
                "summary": collected["content"],
                "tool_results": collected["tool_results"],
            },
        )
