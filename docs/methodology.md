# Stock-EGON 方法论

## 定位

Stock-EGON 的美股日报和周报是持仓复盘系统，不是自动交易系统。它把公开行情、持仓权重、新闻风险和组合约束合成研究标签，用于回答“今天该重点看什么、为什么、风险位在哪里”。所有动作标签都不是交易指令，真实交易前必须回到券商、正式行情源和个人风险约束复核。

## 参考来源

本项目明确参考 `ZhuLinsen/daily_stock_analysis` 的工程和策略组织方式。参考点包括 GitHub Actions 定时运行、Secrets 管理、多市场数据 provider、新闻源可插拔、通知推送，以及把自然语言策略能力包称为 strategy skill 的做法。

`daily_stock_analysis/strategies/README.md` 把策略写成 YAML skill，并给出核心交易理念：严进策略、趋势交易、量能确认、买点偏好、风险排查、量价配合和强势趋势股放宽。本项目吸收这些理念，但不复制其完整 Web/API/Bot 系统。

源链接：
- https://github.com/ZhuLinsen/daily_stock_analysis
- https://github.com/ZhuLinsen/daily_stock_analysis/tree/main/strategies
- https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/SKILL.md

当前显式吸收的 strategy skills 是：

- `bull_trend`: 多头排列、MA20 趋势、回踩不追高、跌破 MA20 降低看多权重。
- `volume_breakout`: 放量突破、量能确认、突破后乖离率仍需控制，避免追高。
- `event_driven`: 新闻和事件先分类，负面事件风险优先，动作必须有失效条件。
- `growth_quality`: 成长质量框架进入方法论，但当前 yfinance 路径缺少稳定财务字段，暂不直接进入打分。

## 当前评分结构

单票评分由五部分构成：趋势、动量、估值占位、风险和组合集中度。趋势主要看 MA20/MA60、收盘价相对 MA20、MA5/MA10/MA20 多头排列和 MA20 乖离。动量主要看 RSI6、成交量相对 5 日均量和放量确认。风险看持仓盈亏、新闻风险标记和事件风险。组合集中度看单票权重、目标权重和账户风险偏好。

评分只用于排序和解释。`add_candidate` 需要总分、风险分和集中度分同时达标；`trim_candidate` 来自低总分、低风险分或高集中度风险；中间区间分为 `watch` 和 `hold`。

## Guardrail

动作建议必须经过 guardrail。数据质量不足、缺少进入区间、缺少风险位或失效条件时，增持候选会降级为重点观察。这个设计来自 `daily_stock_analysis` 的风险排查思想，也符合本项目“正确失败”的原则。

## 还没有解决的问题

当前规则未回测验证前，只能算可解释复盘规则，不能算已验证交易策略。下一步应该做三件事：建立样本 ticker 回测集，记录每次日报建议后的 5/20/60 日表现，校准 MA 乖离、RSI、成交量和单票集中度阈值。若要引入 `growth_quality`，需要先接入稳定的财务字段和估值字段，再把成长、现金流、ROE 和估值承受力写入可测试规则。
