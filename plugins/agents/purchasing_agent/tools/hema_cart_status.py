"""HemaCartStatusTool - 查看盒马购物车状态"""
from __future__ import annotations

import re
from typing import Any

from core.interfaces.tool import BaseTool, ToolResult
from plugins.agents.purchasing_agent.tools._constants import RID_CART_ICON_LAYOUT
from plugins.agents.purchasing_agent.tools._driver_mixin import (
    get_automation_driver, DeviceNotConnectedError, dismiss_popups,
    scroll_down,
)


class HemaCartStatusTool(BaseTool):
    """查看盒马购物车内容"""

    name = "hema_cart_status"
    description = "查看盒马APP购物车中的商品列表和总价。"
    parameters_schema = {
        "type": "object",
        "properties": {},
    }

    def __init__(self) -> None:
        self._registry = None

    def set_registry(self, registry: Any) -> None:
        self._registry = registry

    async def execute(self, **params: Any) -> ToolResult:
        if not self._registry:
            return ToolResult(success=False, error="插件注册表未注入")

        try:
            driver = await get_automation_driver(self._registry)

            # 1. 导航到购物车页面
            already_in_cart = False
            try:
                current = await driver.app_current()
                if "Cart" in current.get("activity", ""):
                    already_in_cart = True
            except Exception:
                pass

            self._report_progress("正在打开购物车...")
            if not already_in_cart:
                cart_tab = await driver.wait_for_element(
                    resource_id=RID_CART_ICON_LAYOUT,
                    timeout=3,
                )
                if not cart_tab:
                    cart_tab = await driver.wait_for_element(
                        content_desc="购物车", timeout=3,
                    )
                if not cart_tab:
                    cart_tab = await driver.wait_for_element(text="购物车", timeout=3)
                if not cart_tab:
                    return ToolResult(success=False, error="未找到购物车入口")
                await driver.tap_element(cart_tab)
                # 等待购物车页面加载（检测数量输入框出现）
                await driver.wait_for_element(
                    content_desc="购买数量", timeout=5,
                )

            await dismiss_popups(driver)

            # 2. 滚动解析购物车全部商品（支持超过一屏）
            self._report_progress("解析购物车商品列表...")
            w, h = await driver.get_screen_size()
            items = await self._parse_cart_all(driver, screen_height=h)

            # 3. 查找总价
            total_price = ""
            total_els = await driver.find_element(content_desc="合计")
            if total_els:
                total_price = total_els[0].text or total_els[0].content_desc or ""
            if not total_price:
                all_tvs = await driver.find_element(class_name="android.widget.TextView")
                for tv in all_tvs:
                    if "合计" in tv.text:
                        total_price = tv.text
                        break

            if not items:
                return ToolResult(
                    success=True,
                    data={"items": [], "item_count": 0, "total_price": "0", "message": "购物车为空"},
                )

            return ToolResult(
                success=True,
                data={
                    "items": items,
                    "item_count": len(items),
                    "total_price": total_price,
                    "message": f"购物车共 {len(items)} 种商品，总计 {total_price}",
                },
            )

        except DeviceNotConnectedError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"查看购物车失败: {e}")

    async def _parse_cart(self, driver: Any, screen_height: int = 1920) -> list[dict]:
        """解析购物车内容。

        使用 driver 抽象层查找元素，位置阈值基于屏幕高度比例：
        - 价格距数量锚点：< 10% 屏幕高度
        - 商品名距价格锚点：2.5%~25% 屏幕高度（名称在上方）
        """
        from core.interfaces.automation import ElementInfo

        price_threshold = int(screen_height * 0.10)
        name_min_dist = int(screen_height * 0.025)
        name_max_dist = int(screen_height * 0.25)

        items: list[dict] = []

        # 1. 找数量元素（content_desc 匹配 "购买数量N"）
        qty_els: list[ElementInfo] = await driver.find_element(
            class_name="android.widget.EditText",
        )
        qty_entries: list[tuple[int, int]] = []
        for el in qty_els:
            m = re.match(r"购买数量(\d+)", el.content_desc)
            if m:
                qty_entries.append((int(m.group(1)), el.bounds[1]))

        if not qty_entries:
            return items

        # 2. 找价格元素（content_desc 以 ￥ 开头）
        price_frames: list[ElementInfo] = await driver.find_element(
            class_name="android.widget.FrameLayout",
        )
        price_entries: list[tuple[str, int]] = []
        for el in price_frames:
            if el.content_desc.startswith("￥"):
                price_entries.append((el.content_desc, el.bounds[1]))

        # 3. 找商品名元素（排除功能性文本）
        _skip_words = {
            "勾选", "选中", "未选中", "按钮", "店铺", "购物车",
            "立即开通", "比加入时降", "去换购", "已满", "可享",
            "免运费", "结算", "全选", "编辑", "删除",
            "历史低价", "活动价", "券后价", "限时", "促销",
            "折扣", "优惠", "满减", "包邮", "热卖",
            "推荐", "换购", "凑单", "领券", "加价购",
            "再买", "已省", "比原价省", "件起售", "同类推荐",
        }
        name_views: list[ElementInfo] = await driver.find_element(
            class_name="android.view.View",
        )
        name_entries: list[tuple[str, int]] = []
        for el in name_views:
            desc = el.content_desc
            if (
                desc
                and len(desc) > 3
                and "," not in desc
                and "，" not in desc
                and not desc.startswith("￥")
                and not any(w in desc for w in _skip_words)
            ):
                name_entries.append((desc, el.bounds[1]))

        # 4. 以数量为锚点匹配价格和商品名
        used_prices: set[int] = set()
        used_names: set[int] = set()

        for item_idx, (qty, qty_top) in enumerate(qty_entries):
            # 匹配最近价格
            price = ""
            best_p_dist = price_threshold + 1
            best_p_idx = -1
            for p_idx, (p_text, p_top) in enumerate(price_entries):
                if p_idx in used_prices:
                    continue
                dist = abs(qty_top - p_top)
                if dist < price_threshold and dist < best_p_dist:
                    best_p_dist = dist
                    best_p_idx = p_idx
                    price = p_text

            if best_p_idx >= 0:
                used_prices.add(best_p_idx)

            # 匹配最近商品名（在价格/数量上方）
            anchor_top = price_entries[best_p_idx][1] if best_p_idx >= 0 else qty_top
            name = ""
            best_n_dist = name_max_dist + 1
            best_n_idx = -1
            for n_idx, (n_text, n_top) in enumerate(name_entries):
                if n_idx in used_names:
                    continue
                dist = anchor_top - n_top  # 名称在上方
                if name_min_dist < dist < name_max_dist and dist < best_n_dist:
                    best_n_dist = dist
                    best_n_idx = n_idx
                    name = n_text

            if best_n_idx >= 0:
                used_names.add(best_n_idx)

            if name:
                items.append({
                    "index": item_idx,
                    "name": name,
                    "price": price,
                    "quantity": qty,
                })

        return items

    async def _has_cart_items_on_screen(self, driver: Any) -> bool:
        """检测当前屏幕是否还有购物车商品（通过"购买数量"输入框判断）。

        购物车商品有 EditText（content_desc="购买数量N"），
        底部推荐区域没有这类元素，以此区分购物车和推荐区域边界。
        """
        qty_els = await driver.find_element(class_name="android.widget.EditText")
        return any(
            re.match(r"购买数量\d+", el.content_desc)
            for el in qty_els
        )

    async def _parse_cart_all(
        self, driver: Any, screen_height: int = 1920, max_scrolls: int = 10,
    ) -> list[dict]:
        """滚动解析购物车全部商品，按名称去重。

        停止条件（任一满足即停）：
        1. 屏幕上已无"购买数量"输入框 → 已滚入推荐区域
        2. 本次滚动未发现新商品 → 已解析完毕
        3. 达到最大滚动次数（兜底防止推荐区域干扰）
        """
        all_items: list[dict] = []
        seen_names: set[str] = set()

        # 首屏解析
        page_items = await self._parse_cart(driver, screen_height=screen_height)
        for item in page_items:
            if item["name"] and item["name"] not in seen_names:
                all_items.append({**item, "index": len(all_items)})
                seen_names.add(item["name"])

        # 滚动加载更多
        for _scroll_round in range(max_scrolls):
            prev_count = len(all_items)
            self._report_progress(f"加载更多商品... ({len(all_items)} 件)")
            await scroll_down(driver, ratio=0.35)

            # 检测是否已滚出购物车区域（进入底部推荐）
            if not await self._has_cart_items_on_screen(driver):
                break

            page_items = await self._parse_cart(driver, screen_height=screen_height)
            for item in page_items:
                if item["name"] and item["name"] not in seen_names:
                    all_items.append({**item, "index": len(all_items)})
                    seen_names.add(item["name"])

            # 没有新商品 → 已解析完毕
            if len(all_items) == prev_count:
                break

        return all_items
