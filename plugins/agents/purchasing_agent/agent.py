"""PurchasingAgent - 采购助手 Agent"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.interfaces.agent import BaseStreamAgent
from core.interfaces.tool import BaseTool


class PurchasingAgent(BaseStreamAgent):
    """通过盒马APP自动化完成商品采购（仅加购物车）"""

    max_tool_rounds = 0  # 不限轮数，按计划任务执行直到 LLM 自然结束

    def __init__(self, context_bus: Any = None, config: dict | None = None):
        super().__init__(context_bus=context_bus, config=config or {})
        self._tools: list[BaseTool] = []

    @property
    def agent_name(self) -> str:
        return "purchasing_agent"

    @property
    def capabilities(self) -> list[str]:
        return [
            "grocery_purchasing",
            "hema_shopping",
            "cart_management",
        ]

    def get_model(self) -> str:
        return self.config.get("model", "volcengine/doubao-seed-2-0-pro-260215")

    def get_tools(self) -> list[BaseTool]:
        return self._tools

    def set_tools(self, tools: list[BaseTool]) -> None:
        """由 PluginRegistry 注入 tools"""
        self._tools = tools

    def get_system_prompt(self, context: dict) -> str:
        from core.prompt_loader import load_prompt
        return load_prompt(
            Path(__file__).parent / "prompts",
            shopping_list=context.get("shopping_list", ""),
        )
