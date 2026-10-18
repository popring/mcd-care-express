# -*- coding: utf-8 -*-
"""场景模板：把「我想表达什么」翻译成「该点什么」。

每个场景给出三样东西：
    budget_hint  建议预算区间（元）——只是建议，最终以用户传入的预算为准
    keywords     选餐关键词，用于在菜单里挑品类（命中即加分，不命中不惩罚）
    cards        心意卡文案模板，{who} 是收件人称呼，{me} 是下单人自称

文案刻意写得像人话，不像模板。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Scene:
    key: str
    label: str
    one_liner: str
    budget_hint: str
    keywords: List[str] = field(default_factory=list)
    cards: List[str] = field(default_factory=list)


SCENES: Dict[str, Scene] = {
    "birthday": Scene(
        key="birthday",
        label="生日",
        one_liner="今天你是唯一的主角",
        budget_hint="60–120 元（2 人份）",
        keywords=["堡", "鸡块", "薯条", "麦旋风", "圆筒", "蛋糕", "派"],
        cards=[
            "{who}，生日快乐。\n薯条要一根根数着吃，快乐要一口口攒着过——\n这一份麦麦，替我抱抱你。",
            "{who}，又长一岁。\n愿你今年所有的等待都有回音，所有的馋都有人管。\n——{me}",
        ],
    ),
    "overtime": Scene(
        key="overtime",
        label="加班夜宵",
        one_liner="别硬扛，先吃点热的",
        budget_hint="30–60 元（1 人份）",
        keywords=["堡", "咖啡", "薯条", "鸡翅", "可乐", "拿铁"],
        cards=[
            "{who}，别改到太晚。\n这单我下单了，热的东西要趁热吃。\n改完这版就下班。",
            "夜还长，胃别空着。\n吃完这顿，把那个 bug 当薯条一样一根根夹掉。\n——{me}",
        ],
    ),
    "exam": Scene(
        key="exam",
        label="考试加油",
        one_liner="考的全会，蒙的全对",
        budget_hint="30–60 元（1 人份）",
        keywords=["堡", "咖啡", "薯饼", "豆浆", "拿铁", "鸡块"],
        cards=[
            "{who}，明天加油。\n考的全都会，蒙的全都对。\n吃完这顿，去把卷子写满。",
            "别紧张。你刷过的题，比这份套餐里的薯条还多。\n——{me}",
        ],
    ),
    "weekend_breakfast": Scene(
        key="weekend_breakfast",
        label="周末早餐",
        one_liner="不用早起，也有人管早饭",
        budget_hint="20–50 元（1–2 人份）",
        keywords=["早餐", "薯饼", "豆浆", "咖啡", "粥", "堡", "蛋"],
        cards=[
            "{who}，睡到自然醒。\n早饭我点好了，按门铃的时候再起。\n——{me}",
            "周末的第一件事，是不用自己想办法吃早饭。\n开门拿一下。",
        ],
    ),
    "sorry": Scene(
        key="sorry",
        label="道歉",
        one_liner="话不好说，先吃点甜的",
        budget_hint="30–80 元（1–2 人份）",
        keywords=["麦旋风", "圆筒", "派", "薯条", "鸡块", "可乐"],
        cards=[
            "{who}，那件事是我没考虑周全。\n话我先写在这儿，甜的部分先送到。\n——{me}",
            "我知道一份麦麦抵不了什么。\n但它能让你在生气的时候，嘴里有东西嚼。",
        ],
    ),
    "thanks": Scene(
        key="thanks",
        label="致谢",
        one_liner="这次真的多亏你",
        budget_hint="40–100 元（2–3 人份）",
        keywords=["堡", "鸡翅", "薯条", "可乐", "咖啡", "分享盒"],
        cards=[
            "{who}，这次真的多亏你。\n别的先不说，这顿我请。\n——{me}",
            "帮了大忙，谢谢。\n分你一半薯条，剩下的算我的心意。",
        ],
    ),
}

DEFAULT_SCENE = "thanks"


def get_scene(key: Optional[str]) -> Scene:
    if not key:
        return SCENES[DEFAULT_SCENE]
    return SCENES.get(key, SCENES[DEFAULT_SCENE])


def list_scenes() -> List[Scene]:
    return [SCENES[key] for key in sorted(SCENES)]


def score_meal(name: Optional[str], scene: Scene) -> int:
    """餐品名命中场景关键词的个数。不命中返回 0，不做负分。"""
    if not name:
        return 0
    return sum(1 for word in scene.keywords if word and word in name)


def pick_card(scene: Scene, index: int = 0) -> str:
    if not scene.cards:
        return ""
    return scene.cards[index % len(scene.cards)]
