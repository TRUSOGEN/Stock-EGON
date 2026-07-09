# Stock-EGON 方法论

## 定位

Stock-EGON 的美股日报和周报是长期持仓复盘系统，不是自动交易系统。它把公开行情、持仓权重、新闻风险和组合约束合成研究标签，用于回答“1 个月、1 个季度和 1 年视角下该重点看什么、为什么、风险位在哪里”。所有动作标签都不是交易指令，真实交易前必须回到券商、正式行情源和个人风险约束复核。

## 参考来源

本项目明确参考 `ZhuLinsen/daily_stock_analysis` 的工程和策略组织方式。参考点包括 GitHub Actions 定时运行、Secrets 管理、多市场数据 provider、新闻源可插拔、通知推送，以及把自然语言策略能力包称为 strategy skill 的做法。

`daily_stock_analysis/strategies/README.md` 把策略写成 YAML skill，并给出核心交易理念：严进策略、趋势交易、量能确认、买点偏好、风险排查、量价配合和强势趋势股放宽。本项目吸收这些理念，但不复制其完整 Web/API/Bot 系统。

源链接：
- https://github.com/ZhuLinsen/daily_stock_analysis
- https://github.com/ZhuLinsen/daily_stock_analysis/tree/main/strategies
- https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/SKILL.md
- CMT Association CMT Program: https://cmtassociation.org/cmt-program/
- CMT Association Learning Objectives: https://cmtassociation.org/cmt-program/learning-objectives/
- SEC Investor.gov Diversification: https://www.investor.gov/introduction-investing/investing-basics/glossary/diversification
- SEC Investor.gov Asset Allocation: https://www.investor.gov/introduction-investing/investing-basics/glossary/asset-allocation
- SEC Investor.gov EDGAR: https://www.investor.gov/introduction-investing/investing-basics/glossary/edgar
- FINRA Stocks: https://www.finra.org/investors/investing/investment-products/stocks
- Kenneth R. French Data Library: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html
- Fama/French 5 Factors description: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_5_factors_2x3.html
- Bailey, Borwein, López de Prado, Zhu, "The Probability of Backtest Overfitting": https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253

当前显式吸收的 strategy skills 是：

- `bull_trend`: 多头排列、MA20 趋势、回踩不追高、跌破 MA20 降低看多权重。
- `volume_breakout`: 放量突破、量能确认、突破后乖离率仍需控制，避免追高。
- `event_driven`: 新闻和事件先分类，负面事件风险优先，动作必须有失效条件。
- `growth_quality`: 成长质量框架进入方法论，但当前 yfinance 路径缺少稳定财务字段，暂不直接进入打分。

## 当前评分结构

单票评分由五部分构成：趋势、动量、估值占位、风险和组合集中度。趋势主要看 MA20/MA60、MA60/MA120、收盘价相对 MA20、短中期均线是否配合季度趋势和 MA20 乖离。动量主要看 RSI24、成交量相对 20 日均量和趋势延续确认。风险看持仓盈亏、新闻风险标记和事件风险。组合集中度看单票权重、目标权重和账户风险偏好。

评分只用于排序和解释。`add_candidate` 需要总分、风险分和集中度分同时达标；`trim_candidate` 来自低总分、低风险分或高集中度风险；中间区间分为 `watch` 和 `hold`。

优化后的解释口径是“技术状态 + 组合约束 + 数据可信度”的复合研究标签。CMT Association 把技术分析定位为识别机会、管理风险、分析市场行为和管理持仓的工具，因此本项目的 MA、RSI、成交量指标只用于判断当前价格行为是否支持月度或季度复盘，不把任何单一指标解释为独立买卖信号。趋势分回答价格是否处在可解释的上升结构中，动量分回答月度强弱是否得到量能支持，风险分回答当前亏损、负面事件和波动是否要求先等风险解除，集中度分回答个股权重是否偏离账户约束。

估值占位暂时不计入真正的 valuation alpha。FINRA 对股票风险的说明强调个股价格受公司经营、市场环境、利率、政治和其他外部因素共同影响；SEC EDGAR 提供 10-K、10-Q、8-K 等公司财务和事件材料；Kenneth R. French Data Library 的五因子说明把 operating profitability、investment、book-to-market 和 market equity 明确定义为可复核字段。基于这些来源，`growth_quality` 进入正式评分前必须有稳定的财务字段、字段口径和缺失值处理规则，最低字段集合应包括营收增长、毛利率或经营利润率、自由现金流或经营现金流、ROE 或 ROIC、净负债或现金覆盖、估值倍数和未来增长承受力。

组合集中度是独立约束，不是技术分的附属项。SEC Investor.gov 把 diversification 定义为把资金分散到多个投资上，以降低单一投资失败对整体组合的冲击；asset allocation 则是把资金分配到股票、债券、现金等类别。Stock-EGON 当前只处理用户给出的美股持仓和现金，因此它不能假装完成完整资产配置，只能在这个子组合内部提示单票权重、现金不足和持仓数量风险。

动作分层采用候选制。`add_candidate` 表示“若用户本来计划按月度或季度再平衡，这只股票优先进入人工复核列表”；`trim_candidate` 表示“集中度、风险或技术状态要求优先复核是否降低敞口”；`watch` 表示“有信息价值但触发条件不足”；`hold` 表示“当前没有足够证据要求改变持仓”。这些标签的排序依据可以解释，但未经过回测前不能声称有预测优势。

## Guardrail

动作建议必须经过 guardrail。数据质量不足、缺少进入区间、缺少风险位或失效条件时，增持候选会降级为重点观察。这个设计来自 `daily_stock_analysis` 的风险排查思想，也符合本项目“正确失败”的原则。

Guardrail 的核心是把“看起来不错”转成“条件完整”。`add_candidate` 至少需要四类条件同时存在：行情质量不低于 `medium`，价格没有显著远离可解释的进入区间，报告中能写出月度或季度风险位和失效条件，风险分和集中度分没有触发硬性拦截。缺失任一条件时，报告应保留原因并降级为 `watch`，因为用户需要的是可执行的复核清单，而不是没有边界的乐观建议。

新闻和事件风险优先于技术分。财报、指引、监管、诉讼、融资、产品事故、管理层变动和重大宏观事件会改变单票风险解释，负面事件未澄清时不能因为 MA 或 RSI 好看而给出增持候选。新闻 provider 失败时可以继续生成核心报告，但必须在 warnings 和市场注释里显式说明新闻增强缺失；核心行情或持仓数据失败时应失败退出。

## 还没有解决的问题

当前规则未回测验证前，只能算可解释复盘规则，不能算已验证交易策略。下一步应该做三件事：建立样本 ticker 回测集，记录每次日报建议后的 5/20/60 日表现，校准 MA 乖离、RSI、成交量和单票集中度阈值。若要引入 `growth_quality`，需要先接入稳定的财务字段和估值字段，再把成长、现金流、ROE 和估值承受力写入可测试规则。

验证路线应先做建议留痕，再做参数校准。每次日报需要保存 ticker、日期、动作标签、总分、各分项、数据质量、触发条件、新闻风险和当日收盘价；之后计算 5/20/60 个交易日相对 SPY 或 QQQ 的超额收益、最大回撤、是否触发风险位和是否发生重大事件。参数校准时先固定样本和评价指标，再比较 MA 乖离、RSI、量能、集中度阈值的敏感性，避免为了让历史结果好看而反复改参数。

回测需要显式防过拟合。Bailey、Borwein、López de Prado 和 Zhu 关于 backtest overfitting 的研究提示，多次试验和参数搜索会让历史表现被高估。本项目在没有 out-of-sample、walk-forward 或类似 purged validation 之前，只能报告“历史复盘表现”，不能把结果写成“已验证策略”。日报语言也应保持克制，优先写“观察、复核、条件、风险位”，少写确定性收益判断。

更高质量的下一版方法论可以加入三层增强：第一层是把市场环境作为上层过滤器，例如 SPY/QQQ 趋势、波动和利率敏感期；第二层是接入授权基本面数据，落地 `growth_quality` 和 valuation guardrail；第三层是把组合层从单票权重扩展到行业、主题和因子暴露，避免 AI、半导体或高 beta 资产在多个 ticker 里重复暴露而未被识别。
