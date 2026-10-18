# WorkBuddy 开发对话上下文

> 本文件用于核验「使用腾讯 WorkBuddy 智能体开发」这一联动活动奖励条件。
> 以下为 2026-10-18 在 WorkBuddy（Windows 桌面端，Agent 模式）中的真实开发过程节选。

## 1. 环境侦察（决定「我到底能自动化到哪一步」）

**我**：你能直接操作我电脑自己去弄吗

**WorkBuddy**：先不写代码，先确认边界。跑了几条命令：

```bash
gh auth status      # → Logged in to github.com account popring，token scopes 含 repo
git config --global user.name   # → popring
gh api repos/M-China/mcd-developer-innovation-challenge --jq '.has_issues,.permissions'
gh api repos/M-China-Official/mcd-developer-innovation-challenge --jq '.has_issues,.permissions'
# → 两个仓 has_issues=true，push=false（非协作者只能发 Issue，够用）
```

结论：**自动化的上限到「建仓 + push + 发报名 Issue」为止**；
MCP Token 需要手机号收验证码、Star 需要真人传播，这三步做不了。

## 2. 规则核查（发现一处会直接导致报名失败的坑）

**WorkBuddy**：README 与 `activityGuidelines.md` 的必备文件清单不一致。
guidelines 里多了一个 **`mcp-config.example.json`**（脱敏 MCP 配置，只允许
环境变量占位符）——只照 README 准备会被判报名失败。

```
必备 5 件：README.md / CONTEST_DECLARATION.md（内容不可改）/
          MCP_INTEGRATION.md / mcp-config.example.json / workbuddy.md
```

另记：同一 GitHub 账号多个项目，只有 Star 最高的进榜。

## 3. 竞品调研（这一步推翻了我的初始判断）

**我**：你去调研一下，看看还有没有什么新方向，看看大家的痛点

**WorkBuddy**：

```bash
curl -sL .../main/RANKING.md | head -80      # 排行榜快照，102 个项目
gh api ".../issues?per_page=100" --jq '.[] | .title'   # 全部报名项目标题
# grep -E "配送|外卖|麦乐送|代下单|异地|取消|退单"  → 零命中
```

三个结论：

1. **省钱类是冠军赛道不是红海**（前三名 560 / 491 / 422 全是省钱类）
2. **积分方向不吸星**（6+ 个项目全在 16–71 星）
3. **`delivery-*` 这一整组工具零命中**——所有人都在做「给自己点」

## 4. 方向决策

**我**：按照第一个你去做吧，做完自己去提交一下

选定「麦麦心意达」：独占 `delivery-*` 工具组 + 异地情感场景。

## 5. 编码（全程 WorkBuddy Agent 模式直接写文件）

按调研结论照抄冠军项目的取胜打法：**零第三方依赖 + fixtures 免 Token 可跑**。

```
src/mcp_client.py   Streamable HTTP 客户端，HttpTransport / FixtureTransport 双传输层
src/adapter.py      响应归一化，「分 → 元」换算的唯一边界
src/scenes.py       六种场景模板与心意卡文案
src/timing.py       麦乐送预约时间窗（提前 ≤ 6 天）
src/care.py         主链路编排 + 预算守门
src/report.py       终端输出 + HTML 心意卡
demo.py             一键演示，同时是端到端回归测试
```

## 6. 排错记录

**第一跑报错**：

```
File "src/adapter.py", line 211, in parse_meals
    result.append(
NameError: name 'result' is not defined
```

原因：改 `parse_meals` 为递归摊平时，把 `result: List[Meal] = []` 一起删掉了。
补回初始化，重跑通过。

**第二跑报错**：`unittest discover` 报 `Start directory is not importable`。
补 `tests/__init__.py` 解决。

**最终**：

```
python demo.py                                  # 链路跑通，5 次 MCP 调用
python -m unittest discover -s tests -t .       # Ran 19 tests ... OK
```

## 7. 关键设计取舍（对话中明确的）

- **金额只信 `calculate-price`**，拿不到就显示「未知」，绝不填 0 冒充免费；
- **`create-order` 默认绝不调用**，必须 `--confirm`，且下单前再算一次价；
- **`delivery-create-address` 只在用户明确给新地址时调用**；
- **预算守门优先于凑出方案**，超预算减配重试，仍超就如实标记；
- **fixtures 是人工构造的结构样本**，不是真实录制——没有 Token 就不假装跑通过。

最后一条是刻意的：排名看 Star，但骗来的 Star 没意义。
