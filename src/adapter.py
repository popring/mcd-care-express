# -*- coding: utf-8 -*-
"""把麦当劳 MCP 的原始响应归一化成领域对象。

两条硬规矩：
    1. **所有金额统一在边界处做一次「分 → 元」换算**，业务层只接触元；
       拿不到就返回 None，绝不填 0 冒充「免费」。
    2. **字段缺失就留空并标记 unknown**，不猜、不补默认值、不用历史价格替代。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

UNKNOWN = "unknown"


def fen_to_yuan(value: Any) -> Optional[float]:
    """分 → 元。None / 非数字 / 负数一律返回 None（宁可少报，不可编造）。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return round(number / 100.0, 2)


def yuan_text(value: Optional[float]) -> str:
    if value is None:
        return "未知"
    return "¥%.2f" % value


def _as_list(payload: Any, *keys: str) -> List[Dict[str, Any]]:
    """从各种可能的包裹结构里抠出列表。"""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        node = payload.get(key)
        if isinstance(node, list):
            return [item for item in node if isinstance(item, dict)]
        if isinstance(node, dict):
            for sub in ("list", "items", "records", "data"):
                inner = node.get(sub)
                if isinstance(inner, list):
                    return [item for item in inner if isinstance(item, dict)]
    return []


def _first(payload: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if payload.get(key) not in (None, ""):
            return payload[key]
    return None


@dataclass
class Address:
    """可配送地址。"""

    address_id: Optional[str] = None
    receiver: Optional[str] = None
    phone: Optional[str] = None
    detail: Optional[str] = None
    tag: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def label(self) -> str:
        parts = [p for p in (self.receiver, self.detail) if p]
        return " · ".join(parts) if parts else UNKNOWN


@dataclass
class Store:
    """可配送门店。"""

    store_id: Optional[str] = None
    name: Optional[str] = None
    address: Optional[str] = None
    distance_km: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def label(self) -> str:
        return self.name or self.store_id or UNKNOWN


@dataclass
class Meal:
    """可售餐品。"""

    code: Optional[str] = None
    name: Optional[str] = None
    price_yuan: Optional[float] = None
    category: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def label(self) -> str:
        base = self.name or self.code or UNKNOWN
        return "%s（%s）" % (base, yuan_text(self.price_yuan))


@dataclass
class Quote:
    """一次算价的结果。"""

    total_yuan: Optional[float] = None
    delivery_fee_yuan: Optional[float] = None
    discount_yuan: Optional[float] = None
    payable_yuan: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def has_payable(self) -> bool:
        return self.payable_yuan is not None


@dataclass
class Order:
    """创建成功的订单。"""

    order_no: Optional[str] = None
    store_name: Optional[str] = None
    payable_yuan: Optional[float] = None
    pay_url: Optional[str] = None
    status: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


def parse_addresses(payload: Any) -> List[Address]:
    items = _as_list(payload, "addresses", "addressList", "data", "list")
    result: List[Address] = []
    for item in items:
        result.append(
            Address(
                address_id=str(_first(item, "addressId", "id", "address_id") or "") or None,
                receiver=_first(item, "receiver", "name", "contactName", "userName"),
                phone=_first(item, "phone", "mobile", "phoneNumber", "contactPhone"),
                detail=_first(item, "address", "detail", "addressDetail", "fullAddress"),
                tag=_first(item, "tag", "label", "addressTag"),
                raw=item,
            )
        )
    return result


def parse_stores(payload: Any) -> List[Store]:
    items = _as_list(payload, "stores", "storeList", "data", "list")
    result: List[Store] = []
    for item in items:
        distance = _first(item, "distance", "distanceKm", "distance_km")
        try:
            distance_km = float(distance) if distance is not None else None
        except (TypeError, ValueError):
            distance_km = None
        result.append(
            Store(
                store_id=str(
                    _first(item, "storeId", "id", "store_id", "restaurantId") or ""
                )
                or None,
                name=_first(item, "storeName", "name", "restaurantName"),
                address=_first(item, "address", "storeAddress"),
                distance_km=distance_km,
                raw=item,
            )
        )
    return result


def _flatten_meals(node: Any, out: List[Dict[str, Any]], seen: set) -> None:
    """递归摊平菜单：官方菜单是「分类 → 子分类 → 餐品」的多层结构。

    只要一个 dict 带得动餐品名字段，就认为它是餐品；其余节点继续往下钻。
    用 id() 去重，避免同一节点被多条路径重复收集。
    """
    if isinstance(node, list):
        for item in node:
            _flatten_meals(item, out, seen)
        return
    if not isinstance(node, dict) or id(node) in seen:
        return
    seen.add(id(node))
    if any(key in node for key in ("name", "mealName", "productName", "title")):
        out.append(node)
        return
    for value in node.values():
        if isinstance(value, (list, dict)):
            _flatten_meals(value, out, seen)


def parse_meals(payload: Any) -> List[Meal]:
    """菜单可能是平铺列表，也可能是多层分类嵌套，两种情况都要能解。"""
    candidates: List[Dict[str, Any]] = []
    _flatten_meals(payload, candidates, set())
    result: List[Meal] = []
    for item in candidates:
        tags = item.get("tags") or item.get("labels") or []
        if isinstance(tags, str):
            tags = [tags]
        price_raw = _first(item, "price", "salePrice", "amount", "priceFen")
        price_yuan = fen_to_yuan(price_raw)
        if price_yuan is None:
            # 某些接口直接给元（小数），这里只接受看起来像元的正数
            try:
                maybe = float(price_raw)
            except (TypeError, ValueError):
                maybe = None
            if maybe is not None and maybe > 0 and maybe < 1000:
                price_yuan = round(maybe, 2)
        result.append(
            Meal(
                code=str(_first(item, "code", "mealCode", "productCode", "id") or "") or None,
                name=_first(item, "name", "mealName", "productName", "title"),
                price_yuan=price_yuan,
                category=_first(item, "category", "categoryName", "categoryId"),
                tags=[str(t) for t in tags],
                raw=item,
            )
        )
    return result


def parse_quote(payload: Any) -> Quote:
    if not isinstance(payload, dict):
        return Quote()
    total = _first(payload, "total", "totalAmount", "totalPrice", "originPrice")
    delivery = _first(payload, "deliveryFee", "deliveryAmount", "shippingFee", "freight")
    discount = _first(payload, "discount", "discountAmount", "promotionAmount", "couponAmount")
    payable = _first(payload, "price", "payAmount", "payable", "actualPrice", "payPrice")
    return Quote(
        total_yuan=fen_to_yuan(total),
        delivery_fee_yuan=fen_to_yuan(delivery),
        discount_yuan=fen_to_yuan(discount),
        payable_yuan=fen_to_yuan(payable),
        raw=payload,
    )


def parse_order(payload: Any) -> Order:
    if not isinstance(payload, dict):
        return Order()
    return Order(
        order_no=str(_first(payload, "orderNo", "orderId", "order_no", "id") or "") or None,
        store_name=_first(payload, "storeName", "store", "restaurantName"),
        payable_yuan=fen_to_yuan(_first(payload, "payAmount", "price", "payable", "amount")),
        pay_url=_first(payload, "payUrl", "pay_url", "paymentUrl", "cashierUrl"),
        status=_first(payload, "status", "orderStatus"),
        raw=payload,
    )
