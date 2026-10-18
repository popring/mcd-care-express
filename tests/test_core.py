# -*- coding: utf-8 -*-
"""纯本地单元测试：不需要 Token、不联网。

覆盖的是「错了会真的害到用户」的那部分：金额换算、菜单摊平、预算守门、
时间窗校验，以及最要紧的一条 —— 不加 confirm 绝不下单。
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.adapter import Meal, Store, fen_to_yuan, parse_meals, parse_quote, yuan_text  # noqa: E402
from src.care import Pick, plan_gift, select_meals, submit_gift  # noqa: E402
from src.mcp_client import FixtureTransport, McpClient, McpError  # noqa: E402
from src.scenes import get_scene, score_meal  # noqa: E402
from src.timing import MAX_ADVANCE_DAYS, check_schedule, parse_when  # noqa: E402


class TestMoney(unittest.TestCase):
    def test_fen_to_yuan(self):
        self.assertEqual(fen_to_yuan(3350), 33.5)
        self.assertEqual(fen_to_yuan(0), 0.0)

    def test_bad_money_is_none_not_zero(self):
        """拿不到就返回 None，绝不填 0 冒充免费。"""
        for bad in (None, "", "abc", {}, [], True, -100):
            self.assertIsNone(fen_to_yuan(bad), "非法金额 %r 应为 None" % (bad,))

    def test_yuan_text(self):
        self.assertEqual(yuan_text(None), "未知")
        self.assertEqual(yuan_text(12.5), "¥12.50")

    def test_quote_fields(self):
        q = parse_quote({"total": 4850, "discount": 500, "deliveryFee": 600, "price": 4950})
        self.assertEqual(q.total_yuan, 48.5)
        self.assertEqual(q.discount_yuan, 5.0)
        self.assertEqual(q.delivery_fee_yuan, 6.0)
        self.assertEqual(q.payable_yuan, 49.5)


class TestMenuParsing(unittest.TestCase):
    def test_flatten_nested_categories(self):
        payload = {
            "categories": [
                {"categoryName": "套餐", "meals": [{"code": "A", "name": "巨无霸三件套", "price": 3350}]},
                {"categoryName": "小食", "meals": [{"code": "B", "name": "中薯条", "price": 1200}]},
            ]
        }
        meals = parse_meals(payload)
        self.assertEqual(len(meals), 2)
        self.assertEqual([m.price_yuan for m in meals], [33.5, 12.0])

    def test_flat_list(self):
        meals = parse_meals([{"name": "圆筒", "price": 600}])
        self.assertEqual(len(meals), 1)
        self.assertEqual(meals[0].price_yuan, 6.0)

    def test_unknown_price_stays_none(self):
        meals = parse_meals([{"name": "神秘新品"}])
        self.assertEqual(len(meals), 1)
        self.assertIsNone(meals[0].price_yuan)


class TestSelection(unittest.TestCase):
    def _menu(self):
        return [
            Meal(code="1", name="巨无霸三件套", price_yuan=33.5),
            Meal(code="2", name="麦辣鸡腿堡三件套", price_yuan=33.5),
            Meal(code="3", name="中薯条", price_yuan=12.0),
            Meal(code="4", name="圆筒冰淇淋", price_yuan=6.0),
            Meal(code="5", name="麦旋风", price_yuan=15.5),
        ]

    def test_staple_comes_first(self):
        picks = select_meals(self._menu(), get_scene("birthday"), 60.0)
        self.assertTrue(picks)
        self.assertIn("堡", picks[0].meal.name, "第一件应当是主食")

    def test_respects_budget(self):
        picks = select_meals(self._menu(), get_scene("birthday"), 45.0)
        total = sum(p.subtotal() or 0 for p in picks)
        self.assertLessEqual(total, 45.0)

    def test_tiny_budget_still_returns_something(self):
        """预算低到离谱时不返回空列表，交给上层标记 over_budget。"""
        picks = select_meals(self._menu(), get_scene("birthday"), 1.0)
        self.assertEqual(len(picks), 1)

    def test_no_priced_meal_returns_empty(self):
        self.assertEqual(select_meals([Meal(name="未知价")], get_scene("birthday"), 60.0), [])

    def test_scene_keyword_scoring(self):
        self.assertGreater(score_meal("麦旋风", get_scene("birthday")), 0)
        self.assertEqual(score_meal("中可乐", get_scene("exam")), 0)


class TestTiming(unittest.TestCase):
    def test_past_time_blocked(self):
        now = datetime(2026, 10, 18, 12, 0)
        result = check_schedule(now - timedelta(hours=1), now)
        self.assertFalse(result.ok)

    def test_beyond_six_days_blocked(self):
        now = datetime(2026, 10, 18, 12, 0)
        result = check_schedule(now + timedelta(days=MAX_ADVANCE_DAYS + 1), now)
        self.assertFalse(result.ok)

    def test_within_window_ok(self):
        now = datetime(2026, 10, 18, 12, 0)
        result = check_schedule(now + timedelta(days=2), now)
        self.assertTrue(result.ok)

    def test_parse_when(self):
        now = datetime(2026, 10, 18, 12, 0)
        self.assertEqual(parse_when("明天早上 9 点", now), datetime(2026, 10, 19, 9, 0))
        self.assertIsNone(parse_when("下下周某个时候", now), "解析不了就该返回 None")


class TestSafety(unittest.TestCase):
    def _client(self):
        return McpClient(FixtureTransport({"delivery-query-addresses": {"addresses": []}}))

    def test_submit_without_confirm_does_nothing(self):
        plan = plan_gift(self._client(), scene_key="birthday", budget=60.0)
        self.assertIsNone(submit_gift(self._client(), plan, confirm=False))

    def test_missing_tool_raises_clear_error(self):
        client = McpClient(FixtureTransport({}))
        with self.assertRaises(McpError):
            client.call_tool("query-meals", {})

    def test_no_address_blocks_plan(self):
        plan = plan_gift(self._client(), scene_key="birthday", budget=60.0)
        self.assertTrue(plan.blocked)
        self.assertTrue(plan.warnings)


if __name__ == "__main__":
    unittest.main()
