# MCP 接入说明

## 1. 使用的 MCP Server

| 项 | 值 |
|---|---|
| 官方仓库 | https://github.com/M-China/mcd-mcp-server |
| 远程地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP |
| 鉴权 | 请求头 `Authorization: Bearer <MCP_TOKEN>` |
| Token 申请 | https://open.mcd.cn/mcp（手机号验证登录 → 控制台 → 激活） |
| 限流 | 每个 Token 600 次/分钟，超限返回 429 |

配置示例见 `mcp-config.example.json`（只含环境变量占位符，不含任何真实凭据）。

## 2. 调用流程

```
initialize ──► notifications/initialized ──► tools/call × N
```

完整业务链路：

| # | Tool | 入参（本项目构造） | 出参用途 |
|---|---|---|---|
| 1 | `delivery-query-addresses` | 空 | 取已有配送地址列表 |
| 2 | `delivery-create-address` | `receiver` / `phone` / `address` / `tag` | **仅在用户给新地址时调用**，返回新建地址 |
| 3 | `delivery-query-stores` | `addressId` | 该地址可配送的门店列表 |
| 4 | `query-meals` | `storeId` | 门店在售菜单（多层分类） |
| 5 | `calculate-price` | `storeId` / `addressId` / `items[]` / `dineType=DELIVERY` | 原价、优惠、配送费、应付 |
| 6 | `create-order` | 同上 | **必须显式 `--confirm`** |

代码位置：`src/care.py::plan_gift`（1–5）与 `submit_gift`（6）。

## 3. 调用过的工具与业务价值

| Tool | 业务价值 |
|---|---|
| `delivery-query-addresses` | 判断「能不能复用已有地址」，避免重复建址 |
| `delivery-create-address` | **本项目核心差异点**：把「对方的地址」写进可配送体系，异地代下单才有起点 |
| `delivery-query-stores` | **异地代下单的可行性闸门**。送不到就是送不到，这一步失败就终止，不往下编 |
| `query-meals` | 拿真实在售菜单，价格随门店和时段变化，不写死 |
| `calculate-price` | 唯一的金额来源，杜绝模型幻觉价格 |
| `create-order` | 闭环终点，返回订单号与支付链接 |

### 未使用的工具及原因

未使用 `query-my-coupons` / `available-coupons` / `auto-bind-coupons` /
`list-nutrition-foods` / `order-list` / `cancel-order` 等。

原因：本项目定位是「把一份心意送出去」，不是「把这一单买到最便宜」。
优惠券优化已有成熟参赛项目做得很好，重复一遍没有增量价值，反而会让边界模糊。
**刻意不做，比堆功能更重要。**

## 4. 实测记录与未验证项（诚实口径）

### 已验证（本地，19 个单元测试 + 端到端 demo）

- 多层分类菜单能被正确递归摊平（`tests/test_core.py::TestMenuParsing`）
- 「分 → 元」换算只在 adapter 边界发生，非法值一律返回 `None` 而非 0
- 预算守门：超预算减配重试，仍超则置 `over_budget`，不硬凑方案
- 时间窗校验：过期 / 超过 6 天均被拦下
- 安全边界：不加 `--confirm` 时 `create-order` 一次都不会被调用

### 未验证（开发时无可用 Token）

- `calculate-price` 与 `create-order` 的**请求体字段名**。
  官方只公开了 Tool 描述，未公开字段级文档。本项目按描述推断构造，
  代码内以 `src/care.py::PAYLOAD_SCHEMA_VERIFIED = False` 显式标注。
  首次联网若报参数错误，只需改 `_price_arguments()` 一处。
- 真实响应体结构。`fixtures/` 为人工构造的结构样本，非真实录制。
  详见 `fixtures/README.md`。

### 复现方式

```bash
export MCD_MCP_TOKEN=你的Token
python demo.py --live --scene birthday --budget 80
```

## 5. 已知坑位

| 现象 | 原因 | 处理 |
|---|---|---|
| 401 | Token 无效/过期，或 endpoint 填错 | 确认是 `https://mcp.mcd.cn`，且 Authorization 头带真实 Token |
| 429 | 超过 600 次/分钟 | 降低调用频率 |
| 拿到 `Mcp-Session-Id` 却仍 401 | 未回传会话 ID | 本项目在 `HttpTransport` 中自动回传该响应头 |
| 响应是 `data:` 开头的 SSE | Streamable HTTP 允许两种响应体 | `_parse_body()` 同时支持裸 JSON 与 SSE |

## 6. 合规

- 本项目非麦当劳官方产品，麦当劳及相关商标归其权利人所有；
- 使用麦当劳 MCP 服务须遵守《麦当劳 MCP 服务规则》与《使用条款》；
- 不存储、不上传、不转发用户 Token 与任何个人信息；Token 只从环境变量读取。
