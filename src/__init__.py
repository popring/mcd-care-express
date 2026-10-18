# -*- coding: utf-8 -*-
"""麦麦心意达：异地代下单 Skill。

模块划分：
    mcp_client  传输层可替换的 MCP 客户端（零第三方依赖）
    adapter     把 MCP 原始响应归一化成领域对象，负责「分 → 元」换算
    scenes      场景模板（生日 / 加班 / 考试 / 周末早餐 / 道歉 / 致谢）
    timing      麦乐送预约时间窗校验（官方口径：最多提前 6 天）
    care        主链路编排：地址 → 门店 → 选餐 → 算价 → （确认后）下单
    report      终端与 HTML 两种输出
"""

__all__ = ["mcp_client", "adapter", "scenes", "timing", "care", "report"]

__version__ = "1.0.0"
