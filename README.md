# Stock-EGON

把持仓、行情和新闻整理成一份每天能读完的复盘报告。

Stock-EGON 主要用于美股持仓跟踪：收盘后计算组合盈亏、技术指标和集中度，生成日报或周报，通过邮件发送。也保留了一组 A 股命令行工具，用来筛选股票、诊断个股和回测经典策略。

[配置向导](https://trusogen.github.io/Stock-EGON/config-wizard.html) · [部署教程](docs/github-actions-beginner.md) · [分析方法](docs/methodology.md) · [原理与数据流](docs/principle.md)

## 能做什么

- **持仓复盘**：查看组合市值、现金比例、单票权重和盈亏，按风险与关注优先级组织报告。
- **技术分析**：结合均线、RSI 和量能生成评分，列出需要复核的持仓及触发条件。
- **研究材料整理**：补充市场环境、财务字段、新闻和指定作者观点，保留来源与核验状态。
- **邮件推送**：GitHub Actions 定时生成日报、周报，可在正文加入价格与成交量图，也支持手动补发。
- **可选 AI 分析**：根据本次证据补充判断、反向证据和待核验事项。未配置模型或调用失败时，仍发送规则报告。
- **A 股 CLI**：市场概览、多因子筛选、个股诊断，以及均线交叉、MACD、RSI、布林带策略回测。

美股规则尚未完成策略回测，报告用于研究和人工复核，不执行交易。

## 先在本地试一下

工作流使用 Python 3.12。本地可创建独立环境后安装依赖：

```bash
git clone https://github.com/TRUSOGEN/Stock-EGON.git
cd Stock-EGON
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

用仓库中的示例持仓生成日报：

```bash
mkdir -p reports
python scripts/us_daily_report.py --portfolio-file config/portfolio.example.json > reports/us-daily-report.json
```

示例文件使用虚构持仓。输出是 JSON，`data.report_markdown` 中是可直接阅读的报告正文；生成报告需要联网获取行情，不需要 LLM key。

生成周报：

```bash
python scripts/us_weekly_review.py --portfolio-file config/portfolio.example.json > reports/us-weekly-review.json
```

自己的持仓可以通过 `--portfolio-file` 指定本地文件，或通过环境变量 `PORTFOLIO_JSON` 传入。字段说明见[持仓输入模板](docs/portfolio-input-template.md)，真实持仓请保存在仓库外。

## 配置每日邮件

1. Fork 到自己的 GitHub 账号，在 `Actions` 中启用 `US Stock Portfolio Report`。
2. 打开 `Settings → Secrets and variables → Actions → Secrets`，添加下表中的持仓与邮箱配置。
3. 在 `Actions → US Stock Portfolio Report → Run workflow` 中选择 `daily`，手动运行一次并检查邮件和运行结果。

| Secret | 填写内容 |
| --- | --- |
| `PORTFOLIO_JSON` | 完整持仓 JSON，可从示例文件开始修改 |
| `EMAIL_ADDRESS` | QQ 邮箱地址，默认同时作为发件人与收件人 |
| `EMAIL_AUTH_CODE` | QQ 邮箱的 SMTP 授权码 |
| `DEEPSEEK_API_KEY` | 可选，启用 DeepSeek 分析 |
| `BRAVE_API_KEY` / `TAVILY_API_KEY` / `SERPAPI_API_KEY` | 可选，配置已有的新闻搜索服务凭证 |

持仓、邮箱授权码和 API key 都放在 Secrets。其他邮箱使用完整 SMTP 配置，见[部署说明](docs/us-stock-agent-deployment.md)；火山方舟和其他 OpenAI-compatible 服务见[LLM 配置](docs/llm-config-guide.md)。

不想手写 JSON，可以使用[网页版配置向导](https://trusogen.github.io/Stock-EGON/config-wizard.html)。它在浏览器本地整理配置并生成 GitHub CLI 命令，需要在自己的终端执行。

默认按北京时间周二至周六 08:17 尝试发送日报，周六 09:17 尝试发送周报，各有两次间隔 20 分钟的补跑；成功发送后会去重。GitHub 定时任务可能延迟，具体调度和补发方式见[部署说明](docs/us-stock-agent-deployment.md#定时规则)。

开启正文图表可将 `EMAIL_INCLUDE_CHARTS` 设为 `true`。暂停时在 Actions 中选择 `Disable workflow`，或在 Variables 中设置 `REPORT_ENABLED=false`。

Actions 的 `us-stock-report` artifact 只保存脱敏发送回执，完整报告通过邮件投递。SMTP 返回成功表示服务器接受邮件，最终是否进入收件箱仍需检查。

## 报告里的判断怎么来

行情默认来自 yfinance，使用最近完整美股常规交易日的收盘价。快照、指标和邮件图表复用同一批日线，程序检查交易日、证券身份、币种和价格一致性。

规则评分考虑趋势、动量、持仓盈亏、新闻风险和组合集中度。目前估值项固定为 50 分，新增财务材料只供研究分析，还没有进入评分。`add_candidate`、`trim_candidate`、`hold`、`watch` 分别表示优先复核增持、减持、维持和观察；数据质量不足或缺少触发条件时，增持候选会降级为观察。

可选的模型分析围绕市场环境、经营与估值、事件催化、价格行为、指定作者观点和组合风险展开。价格、盈亏、评分与动作标签由 Python 计算；模型分析作为独立段落追加，并接受引用、覆盖范围和数字校验。校验通过仍需人工判断推断是否成立。

需要了解权重、阈值、数据缺口和验证计划，见[方法论](docs/methodology.md)。

## A 股工具

```bash
# 多因子选股
python scripts/stock_screener.py --top 10 --strategy multi_factor --min-price 2 --max-price 100

# 个股诊断
python scripts/stock_diagnosis.py --code 000001 --name 平安银行

# 大盘与板块概览
python scripts/market_overview.py

# 均线交叉回测
python scripts/backtest.py --code 600519 --strategy ma_cross --days 365
```

这些工具通过 AKShare 获取数据，统一返回带 `ok`、`warnings`、`errors` 和 `data` 的 JSON。行情接口失败或关键数据异常时返回 `ok=false`，并以非零状态退出。回测会同时输出手续费、滑点和成交假设。

## 使用前需要知道

- AKShare 和 yfinance 依赖公开数据源，可能延迟、限流或变更。当前接入适合个人研究，不保证交易级行情服务。
- 技术区间来自历史数据；规则分数和候选标签没有经过收益验证。拆股后请按券商口径核对股数与成本。
- 新闻搜索结果与作者观点保留原链接和时效信息，搜索覆盖不完整，也不能代替原始披露核验。

## 文档与源码

| 入口 | 内容 |
| --- | --- |
| [原理文档](docs/principle.md) | 数据结构、计算流程、错误处理和校验规则 |
| [方法论](docs/methodology.md) | 评分依据、六维研究框架与验证边界 |
| [GitHub 配置教程](docs/github-actions-beginner.md) | 从 Fork 到首次收到邮件 |
| [部署说明](docs/us-stock-agent-deployment.md) | 调度、SMTP、回执、补发与暂停 |
| [LLM 配置](docs/llm-config-guide.md) | 模型服务、参数与失败处理 |
| [微信推送](docs/wechat-bot.md) | 可选企业微信通道及问答功能边界 |

A 股计算位于 `a_stock_quant/`，美股持仓、评分、研究材料与通知位于 `us_stock_agent/`，命令行入口在 `scripts/`，定时任务在 `.github/workflows/us-stock-report.yml`。
