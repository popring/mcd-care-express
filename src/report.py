# -*- coding: utf-8 -*-
"""输出层：终端文本 + 一张可以直接转发的心意卡（HTML）。

不引入任何模板引擎，纯字符串拼接，保证零依赖、可直接用浏览器打开。
"""

from __future__ import annotations

from html import escape
from typing import Optional

from .adapter import yuan_text
from .care import GiftPlan

LIGHT_CSS = """
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
background:#faf7f2;margin:0;padding:32px;color:#2b2118;}
.card{max-width:520px;margin:0 auto;background:#fff;border-radius:18px;
padding:28px 30px;box-shadow:0 8px 28px rgba(120,90,50,.12);}
.brand{font-size:13px;letter-spacing:.18em;color:#b8860b;text-transform:uppercase;}
.title{font-size:22px;font-weight:700;margin:6px 0 2px;}
.sub{font-size:13px;color:#8a7a68;margin-bottom:18px;}
.letter{background:#fffaf0;border-left:4px solid #ffc72c;border-radius:8px;
padding:14px 16px;font-size:15px;line-height:1.9;white-space:pre-line;}
.items{margin:18px 0;border-top:1px dashed #e6dccd;padding-top:14px;}
.row{display:flex;justify-content:space-between;font-size:14px;padding:4px 0;color:#4a3c2e;}
.row.total{font-weight:700;border-top:1px solid #eee;
margin-top:8px;padding-top:10px;font-size:16px;}
.warn{font-size:12.5px;color:#a04a2c;background:#fdf2ee;
border-radius:8px;padding:10px 12px;margin-top:14px;}
.foot{margin-top:18px;font-size:12px;color:#a89a88;text-align:center;}
"""


def render_plan(plan: GiftPlan) -> str:
    lines = []
    lines.append("")
    lines.append("🍔 麦麦心意达 · %s" % plan.scene.label)
    lines.append("   %s" % plan.scene.one_liner)
    lines.append("")

    if plan.schedule is not None:
        lines.append("📅 送达时间：%s" % plan.schedule.summary())
    if plan.address is not None:
        lines.append("📍 收件地址：%s" % plan.address.label())
    if plan.store is not None:
        lines.append("🏪 配送门店：%s" % plan.store.label())
    if not plan.address and not plan.store:
        lines.append("📍 尚未确定地址与门店")

    goods = plan.goods_total()
    if plan.picks:
        lines.append("")
        lines.append("🛒 选品（商品小计 %s）" % yuan_text(goods))
        for pick in plan.picks:
            lines.append("   · %s × %d" % (pick.meal.name or pick.meal.code, pick.quantity))
    if plan.quote is not None:
        q = plan.quote
        lines.append("")
        lines.append("💰 官方算价（calculate-price 回填，非估算）")
        if q.total_yuan is not None:
            lines.append("   原价合计  %s" % yuan_text(q.total_yuan))
        if q.discount_yuan is not None:
            lines.append("   优惠      -%s" % yuan_text(q.discount_yuan))
        if q.delivery_fee_yuan is not None:
            lines.append("   配送费    %s" % yuan_text(q.delivery_fee_yuan))
        lines.append("   应付      %s" % yuan_text(q.payable_yuan))
        if plan.budget is not None:
            flag = "✅ 在预算内" if not plan.over_budget else "⚠️ 超预算"
            lines.append("   预算 %s  %s" % (yuan_text(plan.budget), flag))

    if plan.warnings:
        lines.append("")
        for note in plan.warnings:
            lines.append("⚠️  %s" % note)

    if plan.card:
        lines.append("")
        lines.append("💌 心意卡")
        for line in plan.card.splitlines():
            lines.append("   %s" % line)

    if not plan.blocked and plan.quote is not None and not plan.over_budget:
        lines.append("")
        lines.append("👉 确认无误后加 --confirm 才会真正下单（默认不会）")
    lines.append("")
    return "\n".join(lines)


def render_html(plan: GiftPlan, title: Optional[str] = None) -> str:
    """生成一张可转发的心意卡。金额一律来自算价结果，没有就写「未知」。"""
    heading = title or ("%s · 送你一份麦麦" % plan.scene.label)
    rows = []
    for pick in plan.picks:
        name = escape(pick.meal.name or pick.meal.code or "")
        rows.append(
            '<div class="row"><span>%s × %d</span><span>%s</span></div>'
            % (name, pick.quantity, yuan_text(pick.subtotal()))
        )
    q = plan.quote
    if q is not None:
        if q.discount_yuan is not None:
            rows.append(
                '<div class="row"><span>优惠</span><span>-%s</span></div>'
                % yuan_text(q.discount_yuan)
            )
        if q.delivery_fee_yuan is not None:
            rows.append(
                '<div class="row"><span>配送费</span><span>%s</span></div>'
                % yuan_text(q.delivery_fee_yuan)
            )
        rows.append(
            '<div class="row total"><span>应付</span><span>%s</span></div>'
            % yuan_text(q.payable_yuan)
        )
    warn_html = ""
    if plan.warnings:
        warn_html = '<div class="warn">%s</div>' % escape(" / ".join(plan.warnings))
    where = ""
    if plan.store is not None:
        where = escape("由 %s 配送" % plan.store.label())
    letter = escape(plan.card)
    return (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>%s</title><style>%s</style></head><body><div class=\"card\">"
        "<div class=\"brand\">McDonald&#39;s Care Express</div>"
        "<div class=\"title\">%s</div>"
        "<div class=\"sub\">%s</div>"
        "<div class=\"letter\">%s</div>"
        "<div class=\"items\">%s</div>"
        "%s"
        "<div class=\"foot\">麦麦心意达 · 基于麦当劳中国官方 MCP 能力</div>"
        "</div></body></html>\n"
    ) % (escape(heading), LIGHT_CSS, escape(heading), where, letter, "".join(rows), warn_html)
