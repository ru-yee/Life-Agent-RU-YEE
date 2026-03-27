"""MealAgent - 饮食规划 Agent"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.interfaces.agent import BaseStreamAgent
from core.interfaces.tool import BaseTool


class MealAgent(BaseStreamAgent):
    """AI 驱动的饮食规划 Agent"""

    def __init__(self, context_bus: Any = None, config: dict | None = None):
        super().__init__(context_bus=context_bus, config=config or {})
        self._tools: list[BaseTool] = []

    @property
    def agent_name(self) -> str:
        return "meal_agent"

    @property
    def capabilities(self) -> list[str]:
        return [
            "meal_planning",
            "nutrition_calculation",
            "shopping_list_generation",
            "diet_advice",
            "dish_recommendation",
        ]

    def get_model(self) -> str:
        return self.config.get("model", "volcengine/doubao-seed-2-0-lite-260215")

    def get_tools(self) -> list[BaseTool]:
        return self._tools

    def set_tools(self, tools: list[BaseTool]) -> None:
        """由 PluginRegistry 注入 tools"""
        self._tools = tools
        # 将模型配置注入到需要 LLM 的工具
        for tool in tools:
            if hasattr(tool, "set_model"):
                tool.set_model(self.get_model())

    def get_system_prompt(self, context: dict) -> str:
        """使用 prompt_loader 渲染 system prompt（支持 i18n）"""
        from core.prompt_loader import load_prompt
        return load_prompt(
            Path(__file__).parent / "prompts",
            cuisine_styles=self.config.get("cuisine_styles", []),
            dietary_restrictions=context.get("dietary_restrictions", ""),
            health_goals=context.get("health_goals", ""),
            conversation_history=context.get("conversation_history", []),
        )
