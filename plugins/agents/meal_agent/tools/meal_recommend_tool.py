"""MealRecommendTool - 餐食推荐 Tool"""
from __future__ import annotations

import random

from core.i18n import t
from core.interfaces.tool import BaseTool, ToolResult
from tools.dish_query_tool import DISH_DATABASE


class MealRecommendTool(BaseTool):
    """生成每日或每周餐食推荐"""

    @property
    def name(self) -> str:
        return "meal_recommend"

    @property
    def description(self) -> str:
        return t("tool.meal_recommend.desc")

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": t("tool.param.days"),
                    "default": 1,
                },
                "goal": {
                    "type": "string",
                    "description": t("tool.param.goal"),
                    "default": "均衡",
                },
                "cuisine_preference": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": t("tool.param.cuisine_preference"),
                },
                "daily_calories": {
                    "type": "integer",
                    "description": t("tool.param.daily_calories"),
                    "default": 2000,
                },
                "exclude_flavors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": t("tool.param.exclude_flavors"),
                },
                "exclude_ingredients": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": t("tool.param.exclude_ingredients"),
                },
                "suitability": {
                    "type": "string",
                    "description": t("tool.param.suitability"),
                },
            },
            "required": ["days"],
        }

    async def execute(self, **params) -> ToolResult:
        days = min(params.get("days", 1), 7)
        goal = params.get("goal", "均衡")
        cuisine_pref = params.get("cuisine_preference", [])
        daily_calories = params.get("daily_calories", 2000)
        exclude_flavors = params.get("exclude_flavors", [])
        exclude_ingredients = params.get("exclude_ingredients", [])
        suitability = params.get("suitability", "")

        pool = list(DISH_DATABASE)

        # 排除口味
        if exclude_flavors:
            pool = [
                d for d in pool
                if not any(f in d.get("flavor_profile", "") for f in exclude_flavors)
            ] or pool

        # 排除食材
        if exclude_ingredients:
            def has_excluded(dish: dict) -> bool:
                for ing in dish.get("main_ingredients", []):
                    if any(ex in ing.get("name", "") for ex in exclude_ingredients):
                        return True
                return False
            pool = [d for d in pool if not has_excluded(d)] or pool

        # 适宜人群
        if suitability:
            filtered = [d for d in pool if suitability in d.get("suitability", "")]
            if filtered:
                pool = filtered

        # 菜系偏好
        if cuisine_pref:
            filtered = [d for d in pool if d.get("regional", "") in cuisine_pref]
            if filtered:
                pool = filtered

        # 目标筛选
        if goal == "减脂":
            filtered = [d for d in pool if d.get("calories", 0) <= 300]
            if filtered:
                pool = filtered
        elif goal == "增肌":
            filtered = [d for d in pool if d.get("protein_level", "") in ("高", "中")]
            if filtered:
                pool = filtered
        elif goal == "清淡":
            filtered = [d for d in pool if d.get("flavor_profile", "") in ("鲜", "甜")]
            if filtered:
                pool = filtered

        # 分类菜品池
        staples = [d for d in pool if d["dish_type"] in ("主食", "粥")]
        mains = [d for d in pool if d["dish_type"] in ("荤菜", "荤素菜")]
        sides = [d for d in pool if d["dish_type"] in ("素菜", "凉拌")]
        soups = [d for d in pool if d["dish_type"] == "汤"]
        snacks = [d for d in pool if d["dish_type"] in ("小吃、点心", "饮品")]

        def pick(candidates: list[dict], n: int = 1) -> list[dict]:
            if not candidates:
                return random.sample(pool, min(n, len(pool)))
            return random.sample(candidates, min(n, len(candidates)))

        def dish_info(d: dict) -> dict:
            return {
                "name": d["name"],
                "dish_type": d["dish_type"],
                "calories": d.get("calories", 0),
                "cooking_method": d["cooking_method"],
                "regional": d["regional"],
                "main_ingredients": [
                    i.get("name", "") for i in d.get("main_ingredients", [])[:3]
                ],
            }

        meal_plan = []
        for day in range(1, days + 1):
            breakfast_items = pick(staples or snacks, 1) + pick(sides or snacks, 1)
            lunch_items = pick(mains, 1) + pick(sides, 1) + pick(soups or sides, 1)
            dinner_items = pick(mains, 1) + pick(sides, 1)

            breakfast = [dish_info(d) for d in breakfast_items]
            lunch = [dish_info(d) for d in lunch_items]
            dinner = [dish_info(d) for d in dinner_items]

            b_cal = sum(d["calories"] for d in breakfast)
            l_cal = sum(d["calories"] for d in lunch)
            d_cal = sum(d["calories"] for d in dinner)

            meal_plan.append({
                "day": day,
                "breakfast": breakfast,
                "breakfast_calories": round(b_cal),
                "lunch": lunch,
                "lunch_calories": round(l_cal),
                "dinner": dinner,
                "dinner_calories": round(d_cal),
                "total_calories": round(b_cal + l_cal + d_cal),
            })

        return ToolResult(
            success=True,
            data={
                "meal_plan": meal_plan,
                "days": days,
                "goal": goal,
                "avg_daily_calories": round(
                    sum(d["total_calories"] for d in meal_plan) / days
                ) if meal_plan else 0,
            },
        )
