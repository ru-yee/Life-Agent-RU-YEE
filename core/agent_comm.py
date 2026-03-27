"""AgentCommManager - Agent 间通信管理器"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, TYPE_CHECKING

from loguru import logger

from core.i18n import t
from core.interfaces.tool import BaseTool, ToolResult

if TYPE_CHECKING:
    from core.plugin_registry import PluginRegistry


def _extract_food_items(text: str) -> list[str]:
    """从文本中提取商品列表"""

    # 去掉非食材前缀行（如 "一键加购物车"）和标签前缀（如 "已选食材："）
    # 逐行剥离：删除不含食材的前导行，以及最后一个 "：" 之前的标签
    lines = text.strip().split('\n')
    content_lines: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 去掉 "已选食材：" "采购清单：" 等标签前缀
        cleaned = re.sub(r'^[^：:]*[：:]\s*', '', line)
        # 如果去掉前缀后无内容，且原行也不像食材（无中文食材字符），跳过
        if not cleaned and not re.search(r'[\u4e00-\u9fff].*[\d克斤g]', line):
            continue
        content_lines.append(cleaned or line)
    text = '\n'.join(content_lines)

    # 模式1: 编号列表 "1. 鸡胸肉 500g\n2. 西兰花 1颗"
    numbered = re.findall(r'\d+[.、)\]]\s*(.+?)(?:\n|$)', text)
    if numbered:
        return [item.strip() for item in numbered if item.strip()]

    # 模式2: 顿号/逗号分隔（保护括号内的分隔符）
    # 先将括号内的顿号/逗号替换为占位符，分割后再还原
    protected = re.sub(r'[（(][^)）]*[)）]', lambda m: m.group().replace('、', '\x00').replace('，', '\x01'), text)
    parts = re.split(r'[、，,\n]+', protected)
    items: list[str] = []
    for part in parts:
        part = part.replace('\x00', '、').replace('\x01', '，').strip().rstrip('。；;')
        if not part or len(part) > 30:
            continue
        skip_kws = ['请', '帮', '配送', '地址', '区域', '续接', '已完成',
                     '待继续', '确认', '用户', '选择', '加购物车', '一键']
        if any(kw in part for kw in skip_kws):
            continue
        items.append(part)
    return items


def _food_to_keyword(food: str) -> str:
    """从商品描述中提取搜索关键词（去掉数量后缀和括号内的用量）"""
    # 先去掉括号包裹的数量信息 "猪肉(100g)" → "猪肉"
    keyword = re.sub(r'[（(][^)）]*[)）]', '', food).strip()
    # 再去掉末尾裸露的数量 "鸡胸肉 500g" → "鸡胸肉"
    keyword = re.sub(
        r'[\d.]+\s*(?:g|kg|斤|两|个|颗|根|把|盒|袋|瓶|箱|升|L|ml|份).*$',
        '', keyword, flags=re.I,
    ).strip()
    return keyword or food


def _build_purchase_plan(message: str) -> list[dict[str, Any]]:
    """从采购消息中解析出结构化的工具调用计划（支持续接）"""

    is_resume = bool(re.search(r'续接采购|已完成', message))

    items: list[dict[str, Any]] = []
    done_result = {"success": True, "data": {"skipped": True}, "error": None}

    if is_resume:
        # ── 续接模式：已完成项标记为 done，待继续项为 pending ──
        items.append({"tool": "address_get", "params": {}, "group_id": "setup_0", "done": True, "result": done_result})
        items.append({"tool": "hema_set_location", "params": {}, "group_id": "setup_1", "done": True, "result": done_result})

        done_match = re.search(r'已完成[：:]\s*(.+?)(?:\n|待继续|用户确认|$)', message, re.DOTALL)
        done_foods = _extract_food_items(done_match.group(1)) if done_match else []
        for idx, food in enumerate(done_foods):
            gid = f"food_{idx}"
            items.append({"tool": "hema_search", "params": {"keyword": _food_to_keyword(food)}, "group_id": gid, "done": True, "result": done_result})
            items.append({"tool": "hema_add_cart", "params": {"product_name": food}, "group_id": gid, "done": True, "result": done_result})

        pending_match = re.search(r'待继续[：:]\s*(.+?)(?:\n|用户确认|$)', message, re.DOTALL)
        pending_foods = _extract_food_items(pending_match.group(1)) if pending_match else []
        food_offset = len(done_foods)
        for idx, food in enumerate(pending_foods):
            gid = f"food_{food_offset + idx}"
            items.append({"tool": "hema_search", "params": {"keyword": _food_to_keyword(food)}, "group_id": gid})
            items.append({"tool": "hema_add_cart", "params": {"product_name": food}, "group_id": gid})

        items.append({"tool": "hema_cart_status", "params": {}, "group_id": "cart_status"})
    else:
        # ── 新采购模式 ──
        addr_match = re.search(r'(?:地址|区域)[：:]\s*(\S+)', message)
        if addr_match:
            items.append({"tool": "address_save", "params": {"address": addr_match.group(1)}, "group_id": "setup_0"})
        else:
            items.append({"tool": "address_get", "params": {}, "group_id": "setup_0"})
        items.append({"tool": "hema_set_location", "params": {}, "group_id": "setup_1"})

        list_match = re.search(
            r'(?:清单|商品|采购|买)[：:]\s*(.+?)(?:\n*(?:配送|地址|区域)|$)',
            message, re.DOTALL,
        )
        text = list_match.group(1) if list_match else message
        food_items = _extract_food_items(text)

        for idx, food in enumerate(food_items):
            gid = f"food_{idx}"
            items.append({"tool": "hema_search", "params": {"keyword": _food_to_keyword(food)}, "group_id": gid})
            items.append({"tool": "hema_add_cart", "params": {"product_name": food}, "group_id": gid})

        items.append({"tool": "hema_cart_status", "params": {}, "group_id": "cart_status"})

    return items


class _PlanTracker:
    """跟踪采购计划执行，为 SSE 事件分配 group_id"""

    def __init__(self, plan_items: list[dict[str, Any]]) -> None:
        self._items = plan_items
        self._matched: set[int] = set()
        self._current_group: str | None = None
        self._tcid_to_gid: dict[str, str] = {}
        self._auto_idx = 0  # 无 plan 时自动分配 group_id 的计数器

    def resolve(self, tool_name: str, params: dict[str, Any], tool_call_id: str) -> str | None:
        """根据工具调用信息，匹配计划项并返回 group_id"""
        if not self._items:
            return self._resolve_auto(tool_name, tool_call_id)

        gid: str | None = None
        incoming_kw = (params.get("keyword") or params.get("product_name") or "").lower()

        if tool_name == "hema_search":
            # 1. 关键词模糊匹配
            for pi, item in enumerate(self._items):
                if pi in self._matched or item["tool"] != "hema_search":
                    continue
                plan_kw = (item["params"].get("keyword") or "").lower()
                if plan_kw and incoming_kw and (plan_kw in incoming_kw or incoming_kw in plan_kw):
                    self._matched.add(pi)
                    gid = item.get("group_id")
                    break

            # 2. 重试检测：当前组的 add_cart 未执行，说明是搜索重试
            if gid is None and self._current_group:
                has_pending = any(
                    pi not in self._matched
                    and item["tool"] == "hema_add_cart"
                    and item.get("group_id") == self._current_group
                    for pi, item in enumerate(self._items)
                )
                if has_pending:
                    gid = self._current_group

            # 3. 顺序兜底
            if gid is None:
                for pi, item in enumerate(self._items):
                    if pi not in self._matched and item["tool"] == "hema_search":
                        self._matched.add(pi)
                        gid = item.get("group_id")
                        break

            if gid:
                self._current_group = gid

        elif tool_name == "hema_add_cart":
            gid = self._current_group
            if gid:
                for pi, item in enumerate(self._items):
                    if pi not in self._matched and item["tool"] == "hema_add_cart" and item.get("group_id") == gid:
                        self._matched.add(pi)
                        break

        else:
            # 非食材工具：按工具名顺序匹配
            for pi, item in enumerate(self._items):
                if pi not in self._matched and item["tool"] == tool_name:
                    self._matched.add(pi)
                    gid = item.get("group_id")
                    break

        if gid and tool_call_id:
            self._tcid_to_gid[tool_call_id] = gid
        return gid

    def get_group(self, tool_call_id: str) -> str | None:
        """通过 tool_call_id 查找已知的 group_id"""
        return self._tcid_to_gid.get(tool_call_id)

    def _resolve_auto(self, tool_name: str, tool_call_id: str) -> str | None:
        """无预生成计划时，自动为 search/add_cart 分配 group_id"""
        gid: str | None = None
        if tool_name == "hema_search":
            gid = f"auto_{self._auto_idx}"
            self._current_group = gid
            self._auto_idx += 1
        elif tool_name == "hema_add_cart":
            gid = self._current_group
        elif tool_name in ("address_get", "address_save"):
            gid = "setup_0"
        elif tool_name == "hema_set_location":
            gid = "setup_1"
        elif tool_name == "hema_cart_status":
            gid = "cart_status"
        if gid and tool_call_id:
            self._tcid_to_gid[tool_call_id] = gid
        return gid


class AgentCommManager:
    """管理 Agent 间通信：权限校验、调用执行、日志记录"""

    MAX_CALL_DEPTH = 3
    CALL_TIMEOUT = 30
    # 按 agent 名自定义超时（秒）
    AGENT_TIMEOUTS: dict[str, int] = {
        "purchasing_agent": 7200,  # 采购任务最长 2 小时
    }

    def __init__(self, registry: "PluginRegistry") -> None:
        self._registry = registry
        self._call_chains: dict[str, list[str]] = {}
        self._sse_callback: Any = None

    def get_agent_list(self) -> list[dict[str, Any]]:
        """返回所有已加载 Agent 信息"""
        agents = self._registry.list_plugins(plugin_type="agent")
        result = []
        for a in agents:
            manifest = self._registry.get_manifest(a.name)
            result.append({
                "name": a.name,
                "description": manifest.description if manifest else "",
                "capabilities": a.capabilities,
                "status": a.status,
            })
        return result

    def check_permission(self, source: str, target: str) -> str | None:
        """校验 source 是否有权调用 target，返回错误消息或 None"""
        manifest = self._registry.get_manifest(source)
        if not manifest:
            return t("comm.error.manifest_not_found", source=source)
        allowed = getattr(manifest, "allowed_agents", [])
        if "*" in allowed:
            return None
        if target not in allowed:
            return t("comm.error.no_permission", source=source, target=target)
        return None

    def check_call_chain(self, session_id: str, source: str, target: str) -> str | None:
        """检测循环调用和深度限制，返回错误消息或 None"""
        chain = self._call_chains.get(session_id, [])
        if target in chain:
            return t("comm.error.circular_call", chain="→".join(chain), target=target)
        if len(chain) >= self.MAX_CALL_DEPTH:
            return t("comm.error.depth_exceeded", max_depth=self.MAX_CALL_DEPTH)
        return None

    def set_sse_callback(self, callback: Any) -> None:
        """设置 SSE 事件回调"""
        self._sse_callback = callback

    def _emit_event(self, event_type: str, data: dict) -> None:
        """触发 SSE 事件"""
        if self._sse_callback:
            self._sse_callback(event_type, data)

    async def log_message(
        self,
        session_id: str,
        source: str,
        target: str,
        message: str,
        result: str | None,
        duration_ms: int,
        status: str,
    ) -> None:
        """记录通信日志到数据库"""
        try:
            from core.database import get_db_session
            from core.models.agent_message import AgentMessageRecord

            session = get_db_session()
            record = AgentMessageRecord(
                session_id=session_id,
                source_agent=source,
                target_agent=target,
                message=message,
                result=result,
                duration_ms=duration_ms,
                status=status,
            )
            session.add(record)
            session.commit()
            session.close()
        except Exception as e:
            logger.warning(f"Failed to log agent message: {e}", exc_info=True)


class AgentListTool(BaseTool):
    """系统工具：列出当前已加载的所有 Agent"""

    name = "agent_list"
    parameters_schema = {"type": "object", "properties": {}}

    @property
    def description(self) -> str:
        return t("comm.tool.agent_list.desc")

    def __init__(self, comm_manager: AgentCommManager) -> None:
        self._comm = comm_manager

    async def execute(self, **kwargs: Any) -> ToolResult:
        agents = self._comm.get_agent_list()
        return ToolResult(success=True, data={"agents": agents})


class AgentCallTool(BaseTool):
    """系统工具：调用目标 Agent"""

    name = "agent_call"

    @property
    def description(self) -> str:
        return t("comm.tool.agent_call.desc")

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "target_agent": {
                    "type": "string",
                    "description": t("comm.tool.agent_call.param.target"),
                },
                "message": {
                    "type": "string",
                    "description": t("comm.tool.agent_call.param.message"),
                },
                "context": {
                    "type": "object",
                    "description": t("comm.tool.agent_call.param.context"),
                },
            },
            "required": ["target_agent", "message"],
        }

    def __init__(self, comm_manager: AgentCommManager, source_agent: str) -> None:
        self._comm = comm_manager
        self._source = source_agent

    async def execute(self, **kwargs: Any) -> ToolResult:
        target_name = kwargs.get("target_agent", "")
        message = kwargs.get("message", "")
        session_id = kwargs.get("session_id", "")

        # 1. 权限校验
        error = self._comm.check_permission(self._source, target_name)
        if error:
            return ToolResult(success=False, data=None, error=error)

        # 2. 循环检测 + 深度限制
        error = self._comm.check_call_chain(session_id, self._source, target_name)
        if error:
            return ToolResult(success=False, data=None, error=error)

        # 3. 查找目标 Agent
        target = self._comm._registry.get_agent(target_name)
        if not target:
            return ToolResult(success=False, data=None, error=t("orchestrator.error.agent_not_found", agent=target_name))

        # 4. SSE 通知（开始委派）— 通过 _emit_sse 实时推送
        self._emit_sse("agent_delegate", {
            "source": self._source,
            "target": target_name,
            "message": message,
        })

        # 4.5 为采购任务预生成结构化计划
        plan: list[dict[str, Any]] = []
        if target_name == "purchasing_agent":
            plan = _build_purchase_plan(message)
            # 只有 setup 项没有食材 → 无效计划，不发送
            has_food = any(item["tool"] == "hema_search" for item in plan)
            if plan and has_food:
                self._emit_sse("agent_progress", {
                    "agent": target_name,
                    "type": "plan",
                    "items": plan,
                })
            else:
                plan = []
        tracker = _PlanTracker(plan)

        # 5. 流式执行 — 逐步转发子 Agent 的 SSE 事件给用户
        timeout = self._comm.AGENT_TIMEOUTS.get(
            target_name, self._comm.CALL_TIMEOUT,
        )
        chain = self._comm._call_chains.setdefault(session_id, [])
        chain.append(target_name)
        start_ms = int(time.time() * 1000)

        collected: dict[str, Any] = {"content": "", "tool_results": []}
        # 记录每个 tool_call 的 params 和 group_id，用于历史恢复
        _tc_meta: dict[str, dict[str, Any]] = {}
        try:
            async def _stream_and_collect():
                async for event in target.run(message, session_id):
                    # 转发关键事件给用户（通过 _emit_sse 实时推送）
                    if event.event == "text_delta":
                        collected["content"] += event.data.get("content", "")
                        self._emit_sse("agent_progress", {
                            "agent": target_name,
                            "type": "text",
                            "content": event.data.get("content", ""),
                        })
                    elif event.event == "tool_call":
                        tool = event.data.get("tool", "")
                        tcid = event.data.get("tool_call_id", "")
                        params = event.data.get("params", {})
                        gid = tracker.resolve(tool, params, tcid)
                        # 记录 params 和 group_id 供历史恢复
                        _tc_meta[tcid] = {"params": params}
                        if gid:
                            _tc_meta[tcid]["group_id"] = gid
                        payload: dict[str, Any] = {
                            "agent": target_name,
                            "type": "tool_call",
                            "tool": tool,
                            "tool_call_id": tcid,
                            "params": params,
                        }
                        if gid:
                            payload["group_id"] = gid
                        self._emit_sse("agent_progress", payload)
                    elif event.event == "tool_progress":
                        tcid = event.data.get("tool_call_id", "")
                        gid = tracker.get_group(tcid)
                        payload = {
                            "agent": target_name,
                            "type": "tool_progress",
                            "tool": event.data.get("tool", ""),
                            "tool_call_id": tcid,
                            "step": event.data.get("step", ""),
                        }
                        if gid:
                            payload["group_id"] = gid
                        self._emit_sse("agent_progress", payload)
                    elif event.event == "tool_output_done":
                        tcid = event.data.get("tool_call_id", "")
                        # 合并 params 和 group_id 到 tool_results（供历史恢复）
                        enriched = {**event.data}
                        meta = _tc_meta.get(tcid, {})
                        if meta.get("params"):
                            enriched["params"] = meta["params"]
                        if meta.get("group_id"):
                            enriched["group_id"] = meta["group_id"]
                        collected["tool_results"].append(enriched)
                        gid = tracker.get_group(tcid)
                        payload = {
                            "agent": target_name,
                            "type": "tool_result",
                            "tool": event.data.get("tool", ""),
                            "tool_call_id": tcid,
                            "result": event.data.get("result", {}),
                        }
                        if gid:
                            payload["group_id"] = gid
                        self._emit_sse("agent_progress", payload)
                    elif event.event == "input_request":
                        # 透传用户输入请求（不包装到 agent_progress 中）
                        self._emit_sse("input_request", event.data)
                    elif event.event == "error":
                        raise RuntimeError(event.data.get("error", "Unknown error"))

            await asyncio.wait_for(_stream_and_collect(), timeout=timeout)
            duration_ms = int(time.time() * 1000) - start_ms

            await self._comm.log_message(
                session_id=session_id,
                source=self._source,
                target=target_name,
                message=message,
                result=json.dumps(
                    {"summary": collected["content"]}, ensure_ascii=False,
                ),
                duration_ms=duration_ms,
                status="success",
            )

            self._comm._emit_event("agent_delegate_done", {
                "source": self._source,
                "target": target_name,
                "summary": collected["content"],
            })

            # 检测子 Agent 的工具是否全部失败
            tool_results = collected["tool_results"]
            all_tools_failed = (
                bool(tool_results)
                and all(
                    not r.get("result", {}).get("success", True)
                    for r in tool_results
                )
            )

            if all_tools_failed:
                # 提取第一个工具的错误信息
                first_error = ""
                for r in tool_results:
                    err = r.get("result", {}).get("error", "")
                    if err:
                        first_error = err
                        break
                fail_data: dict[str, Any] = {
                    "summary": collected["content"],
                    "tool_results": tool_results,
                }
                if plan:
                    fail_data["plan"] = plan
                return ToolResult(
                    success=False,
                    data=fail_data,
                    error=t("comm.error.purchase_failed", error=first_error),
                )

            result_data: dict[str, Any] = {
                "summary": collected["content"],
                "tool_results": collected["tool_results"],
            }
            if plan:
                result_data["plan"] = plan
            return ToolResult(success=True, data=result_data)
        except asyncio.TimeoutError:
            duration_ms = int(time.time() * 1000) - start_ms
            await self._comm.log_message(
                session_id=session_id,
                source=self._source,
                target=target_name,
                message=message,
                result=None,
                duration_ms=duration_ms,
                status="timeout",
            )
            return ToolResult(
                success=False, data=None,
                error=t("comm.error.call_timeout", target=target_name, timeout=timeout),
            )
        except Exception as e:
            duration_ms = int(time.time() * 1000) - start_ms
            await self._comm.log_message(
                session_id=session_id,
                source=self._source,
                target=target_name,
                message=message,
                result=str(e),
                duration_ms=duration_ms,
                status="error",
            )
            error_msg = str(e)
            return ToolResult(
                success=False, data=None,
                error=t("comm.error.call_failed", target=target_name, error=error_msg),
            )
        finally:
            if chain and chain[-1] == target_name:
                chain.pop()
            if not chain:
                self._comm._call_chains.pop(session_id, None)
