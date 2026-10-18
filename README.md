# 🍔 麦麦心意达 · mcd-care-express

> 异地给重要的人点一份麦当劳。
> 基于麦当劳中国官方 MCP（`M-China/mcd-mcp-server`）的代下单 Skill，
> 麦乐送从「创建对方地址」到「算价下单」一条链路跑通。

---

## 先看效果

不需要 Token、不联网，`python demo.py` 就能跑出下面这一整段：

```
🍔 麦麦心意达 · 生日
   今天你是唯一的主角

📅 送达时间：时间可行（尽快送达）
📍 收件地址：妈妈 · 江苏省南京市鼓楼区中山北路 200 号 3 栋 502
🏪 配送门店：麦当劳南京鼓楼中山北路餐厅

🛒 选品（商品小计 ¥48.50）
   · 麦辣鸡腿堡三件套 × 1
   · 圆筒冰淇淋 × 1
   · 苹果派 × 1

💰 官方算价（calculate-price 回填，非估算）
   原价合计  ¥48.50
   优惠      -¥5.00
   配送费    ¥6.00
   应付      ¥49.50
   预算 ¥60.00  ✅ 在预算内

💌 心意卡
   妈妈，生日快乐。
   薯条要一根根数着吃，快乐要一口口攒着过——
   这一份麦麦，替我抱抱你。

👉 确认无误后加 --confirm 才会真正下单（默认不会）
```

加 `--html card.html` 还能导出一张可以直接转发的心意卡——
仓库里已经放了一张渲染好的样例：**`examples/card.html`**，浏览器直接打开就能看。

---

## 为什么做这个

**第一，这是一条没人走过的链路。**

麦当劳 MCP 开放了 30 个工具，但本次大赛一百多个参赛项目里，`delivery-*`
这一整组**零命中**——我 grep 过全部报名 Issue，没有一个人碰
`delivery-create-address` / `delivery-query-stores`。所有人都在做「给自己点」，
没有人在做「给别人点」。

**第二，这个需求的痛是真的。**

你在一线城市加班，爸妈在老家的城市。你想给他们点份吃的，但你不熟悉他们家
附近哪家店能送、能送到几号楼、这个时间还送不送。这些事只有真正去走一遍
配送链路才知道——而这正是 MCP 能替你问清楚的。

麦乐送支持**提前 6 天预约**，所以「生日当天早上送到」这种事，是可以安排的。

**第三，它把 MCP 的能力用在了刀刃上。**

不是调一次接口炫技，而是把「地址 → 门店 → 菜单 → 算价 → 下单」串成一条
别人愿意重复用的闭环。每一跳都可能失败，而失败恰恰是这个 Skill 最该说清楚
的部分：地址送不了就是送不了，不会给你编一个方案。

---

## 它做什么

```
delivery-query-addresses   有没有现成地址？
        │  没有
        ▼
delivery-create-address    把爸妈家的地址建进去
        │
        ▼
delivery-query-stores      这个地址到底有几家店能送？  ← 异地代下单的第一道关
        │
        ▼
query-meals                这家店现在卖什么？（递归摊平多层分类菜单）
        │
        ▼
  选品：先定主食，再按场景契合度 + 价格贪心装包，预留 15% 给配送费
        │
        ▼
calculate-price            让官方接口算价，不估算、不猜
        │
        ├── 超预算 → 减一件重试，仍超就如实标记 over_budget，不硬凑
        │
        ▼
   生成心意卡
        │
        ▼
create-order               ⚠️ 必须显式 --confirm 才会调用
```

---

## 快速开始（30 秒，无需 Token）

```bash
git clone https://github.com/popring/mcd-care-express.git
cd mcd-care-express
python demo.py
```

零第三方依赖，只用标准库。Python 3.8+ 均可。

跑单元测试：

```bash
python -m unittest discover -s tests -t .
```

---

## 真实使用

```bash
# 1. 申请 Token（手机号验证登录）：https://open.mcd.cn/mcp
export MCD_MCP_TOKEN=你的Token

# 2. 联网规划（不下单）
python demo.py --live --scene birthday --budget 80 --who 妈妈

# 3. 确认无误后再真的下单
python demo.py --live --scene birthday --budget 80 --who 妈妈 --confirm
```

想在 WorkBuddy 里用对话驱动？见 `workbuddy.md`。

---

## 六种场景

| 场景 | 一句话 | 建议预算 |
|---|---|---|
| `birthday` 生日 | 今天你是唯一的主角 | 60–120 元 |
| `overtime` 加班夜宵 | 别硬扛，先吃点热的 | 30–60 元 |
| `exam` 考试加油 | 考的全会，蒙的全对 | 30–60 元 |
| `weekend_breakfast` 周末早餐 | 不用早起，也有人管早饭 | 20–50 元 |
| `sorry` 道歉 | 话不好说，先吃点甜的 | 30–80 元 |
| `thanks` 致谢 | 这次真的多亏你 | 40–100 元 |

每个场景有自己的选品关键词和几套心意卡文案。文案刻意写得像人话，不像模板。

---

## 三条硬原则

1. **金额一律由 `calculate-price` 回填，绝不估算。**
   拿不到就显示「未知」，绝不填 0 冒充免费。所有「分 → 元」换算只在
   adapter 边界上做一次，业务层只接触元，从架构上杜绝单位错乱。

2. **不擅自改动账号状态。**
   `create-order` 和 `delivery-create-address` 都是写操作。前者必须显式
   `--confirm`；后者只在用户明确提供了新地址时才调用。

3. **预算守门优先于凑出方案。**
   算价超预算就减一件重试，减到最少还超，就如实置 `over_budget=True` 并说明
   原因——不会为了「交出一个方案」而淡掉金额。

---

## 用到的 MCP 工具

| Tool | 用途 | 备注 |
|---|---|---|
| `delivery-query-addresses` | 查已有配送地址 | |
| `delivery-create-address` | 新建对方地址 | 写操作，仅在用户给新地址时调用 |
| `delivery-query-stores` | 查该地址可配送门店 | 异地代下单的可行性闸门 |
| `query-meals` | 查门店在售菜单 | 多层分类，递归摊平 |
| `calculate-price` | 真实算价（含配送费） | 唯一的金额来源 |
| `create-order` | 创建订单 | 写操作，必须 `--confirm` |

未使用：`cancel-order`、`order-list`、`query-my-coupons` 等。
**本项目刻意不做优惠券优化**——那是另一条链路，已经有很好的项目在做，
重复一遍没有价值。边界清晰比功能齐全重要。

---

## 诚实声明（请务必读）

- `fixtures/` 下的响应是**依据官方 Tool 描述人工构造的结构样本**，
  开发时没有可用的真实 Token（申请需要本人手机号接收验证码），
  因此**本项目尚未在 `mcp.mcd.cn` 上完成真实下单闭环验证**。
  真实链路请自行 `python demo.py --live`。
- `calculate-price` / `create-order` 的**请求体字段名是依据 Tool 描述推断的**，
  官方未公开字段级文档。代码中用 `PAYLOAD_SCHEMA_VERIFIED = False` 显式标注，
  首次联网运行若报参数错误，改 `src/care.py::_price_arguments` 一处即可。
- 详见 `MCP_INTEGRATION.md` 与 `fixtures/README.md`。

宁可少报，不可编造。

---

## 项目结构

```
demo.py              一键演示（离线 / 联网 / 确认下单），同时是端到端回归测试
src/mcp_client.py    MCP Streamable HTTP 客户端，传输层可替换
src/adapter.py       响应归一化，「分 → 元」换算的唯一边界
src/scenes.py        场景模板与心意卡文案
src/timing.py        麦乐送预约时间窗校验（提前 ≤ 6 天）
src/care.py          主链路编排与预算守门
src/report.py        终端输出 + HTML 心意卡
fixtures/            离线演示用的结构样本（含口径说明）
tests/               19 个纯本地单元测试
```

---

## 许可

MIT。本项目非麦当劳官方产品，麦当劳及相关商标归其权利人所有。
