# -*- coding: utf-8 -*-
"""主链路编排：地址 → 门店 → 选餐 → 算价 → 心意卡 →（确认后）下单。

两条安全边界：
    1. `create_order` 属于写操作，**默认绝不调用**。`submit_gift` 必须显式传
       confirm=True 才会下单，且下单前会再算一次价；
    2. 预算守门：算价结果超出预算时，先尝试减配重试，仍然超就如实置
       over_budget=True，绝不为了「凑出一个方案」而虚报金额。

关于请求体字段：麦当劳 MCP 的 `calculate-price` / `create-order` 只公开了
Tool 描述，未公开字段级文档。本模块按描述推断构造 payload，并用
PAYLOAD_SCHEMA_VERIFIED 明确标注「未经真实调用验证」——宁可少报，不可编造。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .adapter import (
    Address,
    Meal,
    Order,
    Quote,
    Store,
    parse_addresses,
    parse_meals,
    parse_order,
    parse_quote,
    parse_stores,
    yuan_text,
)
from .scenes import Scene, get_scene, pick_card, score_meal
from .timing import ScheduleCheck, check_schedule

PAYLOAD_SCHEMA_VERIFIED = False  # calculate-price / create-order 的请求体字段未经真实调用验证

MAX_ITEMS = 6
DELIVERY_RESERVE_RATIO = 0.85  # 预留 15% 给配送费与可能的溢价


@dataclass
class Pick:
    meal: Meal
    quantity: int = 1

    def subtotal(self) -> Optional[float]:
        if self.meal.price_yuan is None:
            return None
        return round(self.meal.price_yuan * self.quantity, 2)


@dataclass
class GiftPlan:
    scene: Scene
    budget: Optional[float]
    address: Optional[Address] = None
    store: Optional[Store] = None
    picks: List[Pick] = field(default_factory=list)
    quote: Optional[Quote] = None
    schedule: Optional[ScheduleCheck] = None
    over_budget: bool = False
    card: str = ""
    warnings: List[str] = field(default_factory=list)
    blocked: bool = False  # 链路中断（无地址 / 无门店 / 时间不可行）

    def goods_total(self) -> Optional[float]:
        total = 0.0
        for pick in self.picks:
            sub = pick.subtotal()
            if sub is None:
                return None
            total += sub
        return round(total, 2)


def resolve_address(client, address_id: Optional[str] = None,
                    new_address: Optional[Dict[str, str]] = None) -> Optional[Address]:
    """优先用已有地址；没有且提供了新地址则创建。

    `delivery-create-address` 是写操作，只在用户明确给了 new_address 时才调用。
    """
    try:
        payload = client.call_tool("delivery-query-addresses", {})
    except Exception as exc:  # noqa: BLE001 - 传输层错误要转成可读提示
        raise RuntimeError("查询配送地址失败：%s" % exc) from exc
    addresses = parse_addresses(payload)
    if address_id:
        for addr in addresses:
            if addr.address_id == address_id:
                return addr
    if addresses and not new_address:
        return addresses[0]
    if new_address:
        try:
            payload = client.call_tool("delivery-create-address", dict(new_address))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("创建配送地址失败：%s" % exc) from exc
        created = parse_addresses(payload)
        if created:
            return created[0]
    return addresses[0] if addresses else None


def find_stores(client, address: Address) -> List[Store]:
    arguments: Dict[str, Any] = {}
    if address.address_id:
        arguments["addressId"] = address.address_id
    payload = client.call_tool("delivery-query-stores", arguments)
    return parse_stores(payload)


def load_menu(client, store: Store) -> List[Meal]:
    arguments: Dict[str, Any] = {}
    if store.store_id:
        arguments["storeId"] = store.store_id
    payload = client.call_tool("query-meals", arguments)
    return parse_meals(payload)


STAPLE_WORDS = ("堡", "套餐", "主食", "卷")


def _is_staple(meal: Meal) -> bool:
    text = "%s %s" % (meal.name or "", meal.category or "")
    return any(word in text for word in STAPLE_WORDS)


def _pick_staple(ranked: List[Meal], cap: float) -> Optional[Meal]:
    """先定一份主食 —— 送人只送小食和甜筒不成体统。"""
    for meal in ranked:
        if (meal.price_yuan or 0.0) <= cap and _is_staple(meal):
            return meal
    return None


def select_meals(meals: List[Meal], scene: Scene, budget: Optional[float]) -> List[Pick]:
    """先定主食，再按场景契合度与价格贪心装包，为配送费预留余量。

    只装价格已知的餐品 —— 价格未知的不参与计算，也不塞进购物车。
    """
    priced = [m for m in meals if m.price_yuan is not None]
    if not priced:
        return []
    ranked = sorted(
        priced, key=lambda m: (-score_meal(m.name, scene), m.price_yuan or 0.0, m.name or "")
    )
    if budget is None:
        return [Pick(meal=m) for m in ranked[:3]]

    cap = budget * DELIVERY_RESERVE_RATIO
    staple = _pick_staple(ranked, cap)
    picks: List[Pick] = []
    total = 0.0
    if staple is not None:
        picks.append(Pick(meal=staple))
        total += staple.price_yuan or 0.0
    for meal in ranked:
        if staple is not None and meal is staple:
            continue
        if len(picks) >= MAX_ITEMS:
            break
        price = meal.price_yuan or 0.0
        if total + price <= cap:
            picks.append(Pick(meal=meal))
            total += price
    if not picks:
        # 最便宜的一份都超预算 —— 如实返回，让它触发 over_budget
        picks.append(Pick(meal=min(priced, key=lambda m: m.price_yuan or 0.0)))
    return picks


def _price_arguments(store: Optional[Store], picks: List[Pick],
                     address: Optional[Address]) -> Dict[str, Any]:
    items = []
    for pick in picks:
        if pick.meal.code:
            items.append({"code": pick.meal.code, "quantity": pick.quantity})
    arguments: Dict[str, Any] = {"items": items, "dineType": "DELIVERY"}
    if store and store.store_id:
        arguments["storeId"] = store.store_id
    if address and address.address_id:
        arguments["addressId"] = address.address_id
    return arguments


def quote_gift(client, store: Optional[Store], picks: List[Pick],
               address: Optional[Address]) -> Quote:
    payload = client.call_tool("calculate-price", _price_arguments(store, picks, address))
    return parse_quote(payload)


def plan_gift(client, scene_key: Optional[str] = None, budget: Optional[float] = None,
              address_id: Optional[str] = None, new_address: Optional[Dict[str, str]] = None,
              when: Optional[datetime] = None, who: str = "你", me: str = "我",
              card_index: int = 0) -> GiftPlan:
    """跑完整条规划链路。**不会下单。**"""
    scene = get_scene(scene_key)
    plan = GiftPlan(scene=scene, budget=budget)

    # 1. 时间窗口
    plan.schedule = check_schedule(when)
    if not plan.schedule.ok:
        plan.blocked = True
        plan.warnings.append("送达时间不可行：%s" % plan.schedule.summary())

    # 2. 地址 —— 异地代下单的第一道关：能不能送
    try:
        plan.address = resolve_address(client, address_id=address_id, new_address=new_address)
    except RuntimeError as exc:
        plan.blocked = True
        plan.warnings.append(str(exc))
        return plan
    if plan.address is None:
        plan.blocked = True
        plan.warnings.append("没有可用的配送地址，也未提供新地址 —— 链路到此中断")
        return plan

    # 3. 可配送门店
    stores = find_stores(client, plan.address)
    if not stores:
        plan.blocked = True
        plan.warnings.append("该地址没有可配送的门店（%s）—— 换个地址或改成到店取餐" % plan.address.label())
        return plan
    plan.store = stores[0]
    if len(stores) > 1:
        plan.warnings.append("共 %d 家门店可配送，默认取第一家：%s" % (len(stores), plan.store.label()))

    # 4. 菜单与选品
    meals = load_menu(client, plan.store)
    if not meals:
        plan.blocked = True
        plan.warnings.append("该门店当前没有可解析的菜单数据 —— 可能是时段无供应")
        return plan
    plan.picks = select_meals(meals, scene, budget)

    # 5. 真实算价（预算守门：超了就减配重试）
    for attempt in range(3):
        plan.quote = quote_gift(client, plan.store, plan.picks, plan.address)
        payable = plan.quote.payable_yuan
        if payable is None:
            plan.warnings.append("接口未返回应付金额，无法判断是否超预算（不猜测）")
            break
        if budget is None or payable <= budget:
            break
        if len(plan.picks) <= 1:
            plan.over_budget = True
            plan.warnings.append(
                "已减到最少仍超预算：应付 %s > 预算 %s，不再硬凑方案" % (yuan_text(payable), yuan_text(budget))
            )
            break
        plan.picks = plan.picks[:-1]
        plan.warnings.append("第 %d 次算价超预算，减少一件后重试" % (attempt + 1))
    else:
        plan.over_budget = True

    plan.card = pick_card(scene, card_index).format(who=who, me=me)
    return plan


def submit_gift(client, plan: GiftPlan, confirm: bool = False) -> Optional[Order]:
    """真正下单。**必须 confirm=True 才会调用 create-order。**"""
    if not confirm:
        return None
    if plan.blocked or plan.address is None or plan.store is None:
        raise RuntimeError("方案不完整，拒绝下单")
    fresh = quote_gift(client, plan.store, plan.picks, plan.address)
    over = (
        plan.budget is not None
        and fresh.payable_yuan is not None
        and fresh.payable_yuan > plan.budget
    )
    if over:
        raise RuntimeError(
            "下单前复核超预算（%s > %s），已中止"
            % (yuan_text(fresh.payable_yuan), yuan_text(plan.budget))
        )
    arguments = _price_arguments(plan.store, plan.picks, plan.address)
    payload = client.call_tool("create-order", arguments)
    return parse_order(payload)
