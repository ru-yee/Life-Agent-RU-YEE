"""ShoppingListTool - 购物清单生成 Tool"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import litellm
from loguru import logger

from core.i18n import t, get_locale
from core.interfaces.tool import BaseTool, ToolResult
from tools.dish_query_tool import DISH_DATABASE


# 根据食材名称推断分类
_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("肉禽蛋", ["肉", "鸡", "鸭", "鹅", "排骨", "蛋", "鹌鹑", "肠", "火腿"]),
    ("水产", ["鱼", "虾", "蟹", "贝", "蛤", "鱿鱼", "海带", "紫菜", "海参", "鲍"]),
    ("蔬菜", ["菜", "瓜", "茄", "豆", "笋", "萝卜", "菇", "蘑菇", "木耳", "藕",
              "芹", "葱", "姜", "蒜", "椒", "番茄", "土豆", "山药", "芋", "莲",
              "油菜", "菠菜", "生菜", "白菜", "花菜", "西兰花", "韭", "芽"]),
    ("米面粮油", ["米", "面", "粉", "油", "酱", "醋", "盐", "糖", "淀粉",
                "料酒", "豆瓣", "耗油", "蚝油", "香油", "花椒", "八角",
                "桂皮", "生抽", "老抽", "味精", "鸡精"]),
    ("豆制品", ["豆腐", "豆干", "豆皮", "腐竹"]),
    ("奶饮", ["奶", "牛奶", "酸奶"]),
    ("水果", ["苹果", "葡萄", "猕猴桃", "橙", "柠檬", "南瓜", "玉米"]),
]

# 不需要采购的物品（饮用水、厨房基础设施等）
_SKIP_INGREDIENTS: set[str] = {
    "水", "饮用水", "清水", "凉水", "温水", "热水", "冰水", "开水",
    "冰块", "冰",
}

# 耐用品分类：默认不勾选（家庭通常已有库存）
_DURABLE_CATEGORIES: set[str] = {"米面粮油"}

# LLM 生成食材的默认模型（快速模型即可）
_DEFAULT_MODEL = "volcengine/doubao-seed-2-0-lite-260215"


def _classify(name: str) -> str:
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(kw in name for kw in keywords):
            return category
    return "其他"


def _should_skip(name: str) -> bool:
    """判断食材是否应从采购清单中排除"""
    return name in _SKIP_INGREDIENTS


async def _llm_generate_merged_list(
    dish_names: list[str],
    model: str = _DEFAULT_MODEL,
) -> list[dict]:
    """用 LLM 一次性生成所有菜品的合并食材清单。

    LLM 负责：去重、合并同一食材的用量、统一单位。
    返回格式: [{"name": "食材名", "amount": "合并后的总用量"}]
    """
    if not dish_names:
        return []

    logger.debug(f"Generating merged list with locale={get_locale()}")
    dishes_text = "、".join(dish_names)
    prompt = f"""请为以下全部菜品生成一份**合并后**的食材采购清单。

菜品: {dishes_text}

要求：
1. 列出所有菜品需要的食材（主料+调料），同一食材只出现一次
2. 同一食材在多道菜中出现时，**合并用量**为一个总量（如两道菜各需猪肉200g和300g → 猪肉 500g）
3. 用量使用常见单位（g/个/颗/根/把等），不要出现"适量""少许"以外的模糊描述
4. 不要包含水、饮用水等不需要采购的物品

严格按以下 JSON 格式返回，不要返回其他内容：
[
  {{"name": "猪肉", "amount": "500g"}},
  {{"name": "盐", "amount": "适量"}}
]"""

    try:
        response = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        content = response.choices[0].message.content.strip()

        # 提取 JSON 数组
        start = content.find("[")
        end = content.rfind("]")
        if start != -1 and end != -1:
            return json.loads(content[start:end + 1])
    except Exception as e:
        logger.error(f"LLM 生成合并食材清单失败: {e}")

    return []


def _fallback_collect_ingredients(dish_names: list[str]) -> dict[str, dict]:
    """兜底：从静态数据库收集食材（简单去重，用量用顿号拼接）"""
    dish_map = {d["name"]: d for d in DISH_DATABASE}
    ingredients: dict[str, dict] = {}

    for dish_name in dish_names:
        dish = dish_map.get(dish_name)
        if not dish:
            continue
        for ing in dish.get("main_ingredients", []):
            name = ing.get("name", "")
            amount = ing.get("amount", "")
            if not name or _should_skip(name):
                continue
            if name not in ingredients:
                ingredients[name] = {"amounts": set(), "count": 0}
            ingredients[name]["count"] += 1
            if amount:
                ingredients[name]["amounts"].add(amount)
        for side in dish.get("side_ingredients", []):
            side_name = side if isinstance(side, str) else side.get("name", "")
            if not side_name or _should_skip(side_name):
                continue
            if side_name not in ingredients:
                ingredients[side_name] = {"amounts": set(), "count": 0}
            ingredients[side_name]["count"] += 1

    return ingredients


class ShoppingListTool(BaseTool):
    """根据菜名列表生成采购清单"""

    _model: str = _DEFAULT_MODEL

    @property
    def name(self) -> str:
        return "shopping_list"

    @property
    def description(self) -> str:
        return t("tool.shopping_list.desc")

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "dish_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": t("tool.param.dish_names"),
                },
            },
            "required": ["dish_names"],
        }

    def set_model(self, model: str) -> None:
        """由 Agent 注入模型配置"""
        self._model = model

    async def execute(self, **params: Any) -> ToolResult:
        dish_names = params.get("dish_names", [])

        # 优先让 LLM 生成合并后的食材清单
        self._report_progress(f"为 {len(dish_names)} 道菜生成食材清单...")
        merged_items = await _llm_generate_merged_list(dish_names, model=self._model)

        if merged_items:
            # LLM 成功 → 直接分类
            categorized: dict[str, list[dict]] = defaultdict(list)
            for item in merged_items:
                name = item.get("name", "")
                if not name or _should_skip(name):
                    continue
                category = _classify(name)
                checked = category not in _DURABLE_CATEGORIES
                categorized[category].append({
                    "name": name,
                    "amount": item.get("amount", ""),
                    "checked": checked,
                })
            total_items = sum(len(v) for v in categorized.values())
        else:
            # LLM 失败 → 兜底：静态数据库 + 简单去重
            logger.warning("LLM 合并清单失败，回落到静态数据库")
            ingredients = _fallback_collect_ingredients(dish_names)
            categorized = defaultdict(list)
            for ing_name, info in sorted(ingredients.items(), key=lambda x: -x[1]["count"]):
                category = _classify(ing_name)
                amounts = sorted(info["amounts"]) if info["amounts"] else []
                checked = category not in _DURABLE_CATEGORIES
                categorized[category].append({
                    "name": ing_name,
                    "amount": "、".join(amounts) if amounts else "",
                    "checked": checked,
                })
            total_items = len(ingredients)

        # 固定分类顺序
        ordered_categories = ["肉禽蛋", "水产", "蔬菜", "豆制品", "米面粮油", "奶饮", "水果", "其他"]
        shopping_list = {
            cat: categorized[cat]
            for cat in ordered_categories
            if cat in categorized
        }

        return ToolResult(
            success=True,
            data={
                "shopping_list": shopping_list,
                "total_items": total_items,
                "total_dishes": len(dish_names),
            },
        )
