"""ShortTermMemory - Redis 热缓存 + PostgreSQL 持久化"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import select, desc

from core.interfaces.memory import BaseMemory, MemoryItem


class ShortTermMemory(BaseMemory):
    """
    对话记忆：PostgreSQL 持久化 + Redis 热缓存。

    写入：先写 PG，再写 Redis
    读取：先查 Redis（快），miss 则回落 PG
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.max_turns: int = self.config.get("max_turns", 30)
        self.ttl_hours: int = self.config.get("ttl_hours", 2)
        self._redis = None
        self._init_redis()

    def _init_redis(self) -> None:
        try:
            import redis
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            self._redis = redis.from_url(redis_url, decode_responses=True)
            self._redis.ping()
            logger.info("ShortTermMemory: Redis connected")
        except Exception as e:
            logger.warning(f"ShortTermMemory: Redis unavailable ({e})")
            self._redis = None

    def _redis_key(self, session_id: str) -> str:
        return f"memory:short_term:{session_id}"

    # ── 写入：PG + Redis 双写 ──────────────────────────────

    async def store(self, key: str, value: Any, **metadata: Any) -> int | None:
        """存储对话轮次。key = session_id, value = {role, content}。返回 PG 记录 id。"""
        # 1. 写入 PostgreSQL
        db_id = await self._store_pg(key, value)

        # 2. 写入 Redis 热缓存
        self._store_redis(key, value)
        return db_id

    async def _store_pg(self, session_id: str, value: Any) -> int | None:
        try:
            from core.database import get_session_factory, ChatMessage
            factory = get_session_factory()
            tool_calls = value.get("tool_calls")
            tool_data = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None
            async with factory() as session:
                msg = ChatMessage(
                    session_id=session_id,
                    role=value.get("role", "user"),
                    content=value.get("content", ""),
                    tool_data=tool_data,
                )
                session.add(msg)
                await session.commit()
                await session.refresh(msg)
                return msg.id
        except Exception as e:
            logger.warning(f"PG store failed: {e}")
            return None

    def _store_redis(self, session_id: str, value: Any) -> None:
        if not self._redis:
            return
        try:
            entry = json.dumps({
                "value": value,
                "timestamp": datetime.now().isoformat(),
            }, ensure_ascii=False)
            rkey = self._redis_key(session_id)
            self._redis.rpush(rkey, entry)
            self._redis.ltrim(rkey, -self.max_turns, -1)
            self._redis.expire(rkey, self.ttl_hours * 3600)
        except Exception as e:
            logger.warning(f"Redis store failed: {e}")

    # ── 读取：Redis → PG 回落 ──────────────────────────────

    async def retrieve(self, query: str, top_k: int = 5) -> list[MemoryItem]:
        """按 session_id 查询对话历史"""
        return await self.retrieve_by_session(query, top_k)

    async def retrieve_by_session(self, session_id: str, n: int = 20) -> list[MemoryItem]:
        """获取指定 session 的最近 N 条对话。Redis 优先，miss 回落 PG。"""
        # 1. 尝试 Redis
        items = self._retrieve_redis(session_id, n)
        if items:
            return items

        # 2. 回落 PostgreSQL
        items = await self._retrieve_pg(session_id, n)

        # 3. 回填 Redis 缓存
        if items:
            self._backfill_redis(session_id, items)

        return items

    def _retrieve_redis(self, session_id: str, n: int) -> list[MemoryItem]:
        if not self._redis:
            return []
        try:
            rkey = self._redis_key(session_id)
            raw_list = self._redis.lrange(rkey, -n, -1)
            if not raw_list:
                return []
            items = []
            for raw in raw_list:
                entry = json.loads(raw)
                items.append(MemoryItem(
                    key=session_id,
                    value=entry["value"],
                    memory_type="short_term",
                    created_at=datetime.fromisoformat(entry["timestamp"]),
                    metadata=entry.get("metadata", {}),
                ))
            return items
        except Exception as e:
            logger.warning(f"Redis retrieve failed: {e}")
            return []

    async def _retrieve_pg(self, session_id: str, n: int) -> list[MemoryItem]:
        try:
            from core.database import get_session_factory, ChatMessage
            factory = get_session_factory()
            async with factory() as session:
                stmt = (
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                    .order_by(desc(ChatMessage.id))
                    .limit(n)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()

            # 反转为时间正序
            rows = list(reversed(rows))
            items = []
            for row in rows:
                val: dict = {"role": row.role, "content": row.content}
                if row.tool_data:
                    try:
                        val["tool_calls"] = json.loads(row.tool_data)
                    except Exception:
                        pass
                items.append(MemoryItem(
                    key=session_id,
                    value=val,
                    memory_type="short_term",
                    created_at=row.created_at or datetime.now(),
                ))
            return items
        except Exception as e:
            logger.warning(f"PG retrieve failed: {e}")
            return []

    def _backfill_redis(self, session_id: str, items: list[MemoryItem]) -> None:
        """将 PG 查询结果回填到 Redis"""
        if not self._redis:
            return
        try:
            rkey = self._redis_key(session_id)
            pipe = self._redis.pipeline()
            pipe.delete(rkey)
            for item in items:
                entry = json.dumps({
                    "value": item.value,
                    "timestamp": item.created_at.isoformat(),
                }, ensure_ascii=False)
                pipe.rpush(rkey, entry)
            pipe.expire(rkey, self.ttl_hours * 3600)
            pipe.execute()
        except Exception as e:
            logger.warning(f"Redis backfill failed: {e}")

    # ── 其他接口 ────────────────────────────────────────────

    async def retrieve_recent(self, n: int = 10) -> list[MemoryItem]:
        """获取最近 N 条对话（跨 session）"""
        try:
            from core.database import get_session_factory, ChatMessage
            factory = get_session_factory()
            async with factory() as session:
                stmt = (
                    select(ChatMessage)
                    .order_by(desc(ChatMessage.id))
                    .limit(n)
                )
                result = await session.execute(stmt)
                rows = list(reversed(result.scalars().all()))
            return [
                MemoryItem(
                    key=row.session_id,
                    value={"role": row.role, "content": row.content},
                    memory_type="short_term",
                    created_at=row.created_at or datetime.now(),
                )
                for row in rows
            ]
        except Exception as e:
            logger.warning(f"PG retrieve_recent failed: {e}")
            return []

    async def clear(self, scope: str = "session") -> None:
        """清除记忆"""
        # 清 Redis
        if self._redis:
            try:
                keys = self._redis.keys("memory:short_term:*")
                if keys:
                    self._redis.delete(*keys)
            except Exception:
                pass

        # 清 PG（仅 scope=all 时）
        if scope == "all":
            try:
                from core.database import get_session_factory, ChatMessage
                from sqlalchemy import delete
                factory = get_session_factory()
                async with factory() as session:
                    await session.execute(delete(ChatMessage))
                    await session.commit()
            except Exception as e:
                logger.warning(f"PG clear failed: {e}")
