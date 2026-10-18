# -*- coding: utf-8 -*-
"""fixtures/ 数据说明 —— 请务必先读这一份。

## 这些响应是合成的，不是真实录制

本项目开发时**没有可用的麦当劳 MCP Token**（申请需要本人手机号接收验证码），
因此 fixtures/ 下的 JSON 是**依据官方 `mcd-mcp-server` README 中的 Tool 描述与
字段命名习惯人工构造的结构样本**，用于验证：

* 多层菜单结构能不能被正确摊平；
* 「分 → 元」换算在边界上是否只做一次；
* 预算守门、减配重试、超预算判定这些**纯业务逻辑**是否成立。

它们**不能**用来证明「本项目已在 mcp.mcd.cn 真实跑通」。真实链路请自行执行：

    export MCD_MCP_TOKEN=你的Token
    python demo.py --live

`--live` 会把真实响应写回 fixtures/（加 `--record` 参数），之后即可离线复现。

## 字段口径

* 所有金额单位为**分**（官方接口口径），例如 3350 表示 ¥33.50；
* `calculate-price` 的 `price` 字段是**应付金额**，`total` 是原价合计；
* `query-meals` 为「分类 → 餐品」嵌套结构，本项目递归摊平。

## 文件与工具的对应关系

| 文件 | 对应 MCP Tool |
|---|---|
| delivery-query-addresses.json | `delivery-query-addresses` |
| delivery-create-address.json | `delivery-create-address` |
| delivery-query-stores.json | `delivery-query-stores` |
| query-meals.json | `query-meals` |
| calculate-price.json | `calculate-price` |
| create-order.json | `create-order` |
