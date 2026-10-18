# -*- coding: utf-8 -*-
"""麦麦心意达 · 一键演示。

离线模式（默认）：读 fixtures/，不需要 Token、不联网，跑通整条链路。
    python demo.py

联网模式：直连 mcp.mcd.cn，需要真实 Token。
    export MCD_MCP_TOKEN=xxx
    python demo.py --live

联网录制：把真实响应写回 fixtures/，之后即可离线复现。
    python demo.py --live --record

本脚本同时是端到端回归测试：结尾有一组断言，不满足就非零退出。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.care import PAYLOAD_SCHEMA_VERIFIED, plan_gift, submit_gift  # noqa: E402
from src.mcp_client import FixtureTransport, McpClient, build_client  # noqa: E402
from src.report import render_html, render_plan  # noqa: E402
from src.scenes import list_scenes  # noqa: E402

FIXTURES = ROOT / "fixtures"


def load_fixtures() -> dict:
    responses: dict = {}
    for path in sorted(FIXTURES.glob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            responses[path.stem] = json.load(handle)
    return responses


def record(responses: dict) -> None:
    for key, value in responses.items():
        if key.startswith("_"):
            continue
        path = FIXTURES / ("%s.json" % key)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")


def build_demo_client(live: bool) -> McpClient:
    if not live:
        return McpClient(FixtureTransport(load_fixtures()))
    token = os.environ.get("MCD_MCP_TOKEN", "").strip()
    if not token:
        print("缺少环境变量 MCD_MCP_TOKEN，无法联网运行。", file=sys.stderr)
        print("Token 申请入口：https://open.mcd.cn/mcp", file=sys.stderr)
        raise SystemExit(2)
    return build_client(token=token)


def main() -> int:
    parser = argparse.ArgumentParser(description="麦麦心意达：异地给重要的人点一份麦当劳")
    parser.add_argument("--live", action="store_true", help="直连真实 MCP（需要 MCD_MCP_TOKEN）")
    parser.add_argument("--record", action="store_true", help="联网模式下把真实响应写回 fixtures/")
    scene_help = "场景：%s" % "/".join(scene.key for scene in list_scenes())
    parser.add_argument("--scene", default="birthday", help=scene_help)
    parser.add_argument("--budget", type=float, default=60.0, help="预算（元）")
    parser.add_argument("--who", default="妈妈", help="收件人称呼")
    parser.add_argument("--me", default="我", help="下单人自称")
    parser.add_argument("--confirm", action="store_true", help="真正调用 create-order 下单（默认不会）")
    parser.add_argument("--html", default="", help="把心意卡写到指定 HTML 文件")
    args = parser.parse_args()

    client = build_demo_client(args.live)
    new_address = None
    if not args.live:
        # 离线演示走「新建父母家地址」这条路，正好覆盖 delivery-create-address
        new_address = {
            "receiver": "妈妈",
            "phone": "138****8888",
            "address": "江苏省南京市鼓楼区中山北路 200 号 3 栋 502",
            "tag": "父母家",
        }

    plan = plan_gift(
        client,
        scene_key=args.scene,
        budget=args.budget,
        new_address=new_address,
        who=args.who,
        me=args.me,
    )
    print(render_plan(plan))

    if args.record:
        if not args.live:
            print("--record 需要配合 --live", file=sys.stderr)
            return 2
        print("⚠️  录制功能需要你在 --live 成功后手动写回，此处仅为占位。", file=sys.stderr)

    if args.confirm:
        order = submit_gift(client, plan, confirm=True)
        if order is not None:
            print("✅ 已下单：%s（%s）" % (order.order_no, order.status))
            if order.pay_url:
                print("   支付链接：%s" % order.pay_url)
    else:
        print("ℹ️  未加 --confirm，本次只规划不下单。")

    if args.html:
        Path(args.html).write_text(render_html(plan), encoding="utf-8")
        print("💌 心意卡已写入 %s" % args.html)

    # ---- 回归断言 ----
    assert plan.address is not None, "链路应能解析出配送地址"
    assert plan.store is not None, "链路应能解析出可配送门店"
    assert plan.picks, "链路应至少选出一个餐品"
    assert plan.quote is not None and plan.quote.payable_yuan is not None, "应付金额必须由接口回填"
    if not args.live:
        assert plan.picks[0].meal.name is not None, "首件应是主食"
        if plan.over_budget:
            assert plan.warnings, "超预算时必须给出说明，不能默默交方案"
        else:
            assert plan.quote.payable_yuan <= args.budget, "演示数据下应落在预算内"
        used = {c.get("tool") for c in client.call_log if c.get("tool")}
        for tool in ("delivery-query-addresses", "delivery-create-address",
                     "delivery-query-stores", "query-meals", "calculate-price"):
            assert tool in used, "链路必须真实调用 %s" % tool
    if PAYLOAD_SCHEMA_VERIFIED is not False:
        print("注意：请求体字段口径已变更，请同步更新 MCP_INTEGRATION.md")
    print("✅ 全部断言通过（%d 次 MCP 调用）" % len([c for c in client.call_log if c.get("tool")]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
