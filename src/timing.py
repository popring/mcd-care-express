# -*- coding: utf-8 -*-
"""麦乐送预约时间窗校验。

官方口径：麦乐送支持预约未来 6 天内的配送订单。因此「提前超过 6 天」和
「时间已过」都是明确不可行的，其余时段是否供应（早餐 / 正餐 / 夜宵）由门店
菜单决定，本模块只做保守提示，不代替菜单判断。

原则：不确定就说不确定。这里只输出「明确不可行」和「需由菜单确认」两类结论，
不会拍胸脯保证某个时段一定有餐。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple

MAX_ADVANCE_DAYS = 6

BREAKFAST_END_HOUR = 10.5  # 早餐通常供应到 10:30
LATE_NIGHT_START_HOUR = 22.0  # 22 点之后按夜宵口径


@dataclass
class ScheduleCheck:
    ok: bool
    target: Optional[datetime]
    reasons: list = None  # type: ignore[assignment]
    segment: str = "unknown"

    def summary(self) -> str:
        if self.ok:
            return "时间可行（%s）" % self.segment
        return "；".join(self.reasons or ["时间不可行"])


def check_schedule(target: Optional[datetime], now: Optional[datetime] = None) -> ScheduleCheck:
    """校验一个期望送达时间是否落在可预约窗口内。"""
    now = now or datetime.now()
    if target is None:
        return ScheduleCheck(ok=True, target=None, reasons=["未指定时间，按尽快送达处理"], segment="尽快送达")
    reasons = []
    if target <= now:
        reasons.append("送达时间已过去（%s）" % target.strftime("%m-%d %H:%M"))
    delta = target - now
    if delta > timedelta(days=MAX_ADVANCE_DAYS):
        reasons.append("麦乐送最多提前 %d 天预约，该时间超出窗口" % MAX_ADVANCE_DAYS)
    hour = target.hour + target.minute / 60.0
    if hour < BREAKFAST_END_HOUR:
        segment = "早餐时段"
    elif hour >= LATE_NIGHT_START_HOUR:
        segment = "夜宵时段（请确认门店 24 小时营业）"
    else:
        segment = "正餐时段"
    ok = not reasons
    return ScheduleCheck(ok=ok, target=target, reasons=reasons or [], segment=segment)


def suggest_window(now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """给出可预约的时间窗口边界。"""
    now = now or datetime.now()
    return now, now + timedelta(days=MAX_ADVANCE_DAYS)


def parse_when(text: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """把「明天早上 9 点」这类说法解析成时间。只支持有限几种写法。

    解析不了就返回 None —— 宁可让用户自己填，也不猜一个错的时间。
    """
    if not text:
        return None
    now = now or datetime.now()
    text = text.strip()
    day_offset = 0
    if text.startswith("今天"):
        day_offset, text = 0, text[2:]
    elif text.startswith("明天"):
        day_offset, text = 1, text[2:]
    elif text.startswith("后天"):
        day_offset, text = 2, text[2:]
    text = text.strip("在的 ")
    hour = None
    minute = 0
    if "早上" in text or "上午" in text:
        hour, text = 9, text.replace("早上", "").replace("上午", "")
    elif "中午" in text:
        hour, text = 12, text.replace("中午", "")
    elif "晚上" in text:
        hour, text = 19, text.replace("晚上", "")
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        if len(digits) <= 2:
            hour = int(digits)
        elif len(digits) == 4:
            hour, minute = int(digits[:2]), int(digits[2:])
        else:
            return None
    if hour is None:
        return None
    if hour > 23 or minute > 59:
        return None
    base = now + timedelta(days=day_offset)
    base = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return base
