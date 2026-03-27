"""DishQueryTool - 菜品查询 Tool"""
from __future__ import annotations

import json
from pathlib import Path

from core.i18n import t
from core.interfaces.tool import BaseTool, ToolResult


def _load_dishes() -> list[dict]:
    """从 demo 数据文件加载菜品"""
    data_file = Path(__file__).parent.parent / "data" / "demo_dishes.json"
    if data_file.exists():
        return json.loads(data_file.read_text(encoding="utf-8"))
    return []


DISH_DATABASE = _load_dishes()


class DishQueryTool(BaseTool):
    """菜品查询工具"""

    @property
    def name(self) -> str:
        return "dish_query"

    @property
    def description(self) -> str:
        return "根据菜系、口味、关键词、烹饪方式等查询菜品信息。可用于查找特定类型的菜品。"

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词（菜名、食材等）",
                },
                "regional": {
                    "type": "string",
                    "description": "菜系：通用家常、川菜、粤菜、湘菜、鲁菜、苏菜、东北菜、西式简餐、日韩餐、东南亚菜",
                },
                "dish_type": {
                    "type": "string",
                    "description": "菜品类型：荤菜、素菜、荤素菜、主食、汤、小吃、饮品、粥",
                },
                "flavor": {
                    "type": "string",
                    "description": "口味偏好：咸、鲜、辣、酸、甜",
                },
                "cooking_method": {
                    "type": "string",
                    "description": "烹饪方式：炒、蒸、煮、烧、炖、凉拌、煎、烤、焖、炸",
                },
                "max_calories": {
                    "type": "integer",
                    "description": "最大卡路里限制",
                },
                "dietary_goal": {
                    "type": "string",
                    "description": "饮食目标：减脂（低卡≤150）、增肌（高蛋白）、清淡（鲜/甜口味）、均衡",
                },
                "suitability": {
                    "type": "string",
                    "description": "适宜人群：老人、儿童、孕妇、高血压患者、糖尿病患者等",
                },
            },
        }

    async def execute(self, **params) -> ToolResult:
        keyword = params.get("keyword", "")
        regional = params.get("regional", "")
        dish_type = params.get("dish_type", "")
        flavor = params.get("flavor", "")
        cooking_method = params.get("cooking_method", "")
        max_calories = params.get("max_calories", 0)
        dietary_goal = params.get("dietary_goal", "")
        suitability = params.get("suitability", "")

        results = []
        for dish in DISH_DATABASE:
            # 关键词匹配（菜名、食材、描述、taste_tag）
            if keyword:
                searchable = (
                    dish.get("name", "")
                    + dish.get("description", "")
                    + dish.get("taste_tag", "")
                    + ",".join(i.get("name", "") for i in dish.get("main_ingredients", []))
                )
                if not any(kw in searchable for kw in keyword.split()):
                    continue

            # 菜系匹配
            if regional and regional not in dish.get("regional", ""):
                continue

            # 菜品类型匹配
            if dish_type and dish_type not in dish.get("dish_type", ""):
                continue

            # 口味匹配
            if flavor and flavor not in dish.get("flavor_profile", ""):
                continue

            # 烹饪方式匹配
            if cooking_method and cooking_method not in dish.get("cooking_method", ""):
                continue

            # 卡路里限制
            if max_calories and dish.get("calories", 0) > max_calories:
                continue

            # 饮食目标筛选
            if dietary_goal:
                cal = dish.get("calories", 0)
                protein = dish.get("protein_level", "")
                fl = dish.get("flavor_profile", "")
                if dietary_goal == "减脂" and cal > 150:
                    continue
                elif dietary_goal == "增肌" and protein not in ("高", "中"):
                    continue
                elif dietary_goal == "清淡" and fl not in ("鲜", "甜"):
                    continue

            # 适宜人群匹配
            if suitability and suitability not in dish.get("suitability", ""):
                continue

            results.append({
                "name": dish["name"],
                "dish_type": dish["dish_type"],
                "cooking_method": dish["cooking_method"],
                "flavor_profile": dish["flavor_profile"],
                "calories": dish["calories"],
                "regional": dish["regional"],
                "taste_tag": dish.get("taste_tag", ""),
                "main_ingredients": dish.get("main_ingredients", []),
                "description": dish.get("description", ""),
            })

        # 按卡路里排序，最多返回 10 个
        results.sort(key=lambda d: d["calories"])
        results = results[:10]

        return ToolResult(
            success=True,
            data={"dishes": results, "total": len(results)},
        )
