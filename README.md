# Stock-EGON

Stock-EGON 是一个股票研究辅助项目，当前包含两部分：基于 AKShare 的 A 股量化分析 CLI，以及面向真实美股持仓的日报、周报、企业微信推送工作流。项目用于研究复盘和风险提示，不提供投资建议、交易指令或自动交易。

## 你要做的三件事

第一步，把仓库保留在 GitHub 私有仓库里，然后打开 `Actions` 页面启用 `US Stock Portfolio Report` workflow。这个 workflow 会在北京时间周二到周六 08:30 生成日报，在北京时间周六 09:00 生成周报，也可以手动运行。

第二步，在 GitHub 仓库的 `Settings` -> `Secrets and variables` -> `Actions` 页面，停留在 `Secrets` 标签页，不要切到 `Variables`。点击 `New repository secret`，`Name` 填 `PORTFOLIO_JSON`，`Secret` 填下面“最小可用配置”里的完整 JSON。真实持仓不要提交到仓库，也不要放到 Variables。

第三步，如果要微信推送，在同一个 `Secrets` 标签页再点一次 `New repository secret`。`Name` 填 `WECHAT_WEBHOOK_URL`，`Secret` 填企业微信群机器人复制出来的完整 webhook 地址。具体从哪里创建机器人、怎么复制 URL、怎么测试，见 [docs/wechat-bot.md](docs/wechat-bot.md)。普通群机器人只能单向推送，不能接收你的追问；交互式问答需要后续单独接企业微信应用、公众号或自建回调服务。

如果你不想手工写 `PORTFOLIO_JSON`，可以把 [docs/portfolio-input-template.md](docs/portfolio-input-template.md) 里的提示词发给 AI，再附上持仓截图或表格，让 AI 只负责整理出可复制的 JSON。

如果你想一次性填持仓、微信和新闻源，可以打开 [docs/config-wizard.html](docs/config-wizard.html)。这个页面会在浏览器本地生成 `PORTFOLIO_JSON` 和 `gh secret set` 命令，方便一次性写入 GitHub Secrets。

## GitHub Secrets 照填表

在 `Actions secrets and variables` 页面里，只使用 `Repository secrets`。点击 `New repository secret` 后按下表填写：

| Name | Secret 填什么 | 是否必填 | 放在哪里 |
|---|---|---:|---|
| `PORTFOLIO_JSON` | 你的完整持仓 JSON | 是 | Secrets |
| `WECHAT_WEBHOOK_URL` | 企业微信群机器人 webhook 完整 URL | 否 | Secrets |
| `SERPAPI_API_KEY` | SerpAPI 新闻搜索 key | 否 | Secrets |
| `TAVILY_API_KEY` | Tavily 新闻搜索 key | 否 | Secrets |
| `BRAVE_API_KEY` | Brave Search key | 否 | Secrets |

不要把这两个值填到 `Variables`，因为 Variables 是明文配置；Secrets 才是加密配置。

## 最小可用配置

`PORTFOLIO_JSON` 示例：

```json
{
  "currency": "USD",
  "cash": 4.66,
  "risk_profile": "aggressive",
  "holdings": [
    {"symbol": "AAPL", "quantity": 3, "cost_basis": null, "target_weight": null},
    {"symbol": "MSFT", "quantity": 2, "cost_basis": null, "target_weight": null}
  ]
}
```

手动运行方式：进入 GitHub `Actions` -> `US Stock Portfolio Report` -> `Run workflow`，`report_type` 选择 `daily` 或 `weekly`。运行完成后，可以在日志里看到 JSON，也可以在 `Artifacts` 下载 `us-stock-report`；配置了 `WECHAT_WEBHOOK_URL` 时，群里会收到 Markdown 版本报告。

## 本地快速开始

安装依赖：

```bash
pip install -r requirements.txt
```

如果使用 Codex 桌面内置 Python 运行时，可将下面命令里的 `python` 替换为实际 Python 路径。

## 快速 CLI 参考

多因子选股：

```bash
python scripts/stock_screener.py --top 10 --strategy multi_factor --min-price 2 --max-price 100
```

个股诊断：

```bash
python scripts/stock_diagnosis.py --code 000001 --name 平安银行
```

大盘与板块概览：

```bash
python scripts/market_overview.py
```

策略回测：

```bash
python scripts/backtest.py --code 600519 --strategy ma_cross --days 365
```

美股每日持仓简报：

```bash
python scripts/us_daily_report.py --portfolio-file config/portfolio.example.json
```

美股每周持仓复盘：

```bash
python scripts/us_weekly_review.py --portfolio-file config/portfolio.example.json
```

本地打开配置向导：

```bash
open docs/config-wizard.html
```

推送已生成的美股报告到企业微信：

```bash
WECHAT_WEBHOOK_URL="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx" \
python scripts/send_wechat_report.py --report-file reports/us-daily-report.json
```

## 输出结构

所有 CLI 输出统一 JSON：

```json
{
  "ok": true,
  "module": "stock_diagnosis",
  "fetched_at": "2026-07-07T09:30:00+08:00",
  "data_time": "2026-07-06",
  "source_api": "ak.stock_zh_a_hist",
  "warnings": ["AKShare 数据来自公开数据源，仅供研究参考，不构成投资建议。"],
  "errors": [],
  "data": {}
}
```

当 AKShare 未安装、接口失败、字段缺失或返回空数据时，CLI 会输出 `ok=false` 的 JSON 并以非零状态退出。

## 数据边界

AKShare 是开源财经数据接口库，可以免费安装和使用；它聚合公开数据源，项目声明数据用于学术研究参考，不构成投资建议，并且部分接口可能因不可控因素被移除。美股工具默认使用 yfinance，yfinance 同样依赖 Yahoo Finance 公开数据，适合研究和个人复盘，不适合作为商业行情 SLA。生产级交易、合规披露或商业行情服务应使用有明确授权、稳定 SLA 和审计机制的数据源。

## GitHub 定时推送

本项目已提供 [.github/workflows/us-stock-report.yml](.github/workflows/us-stock-report.yml)。推荐把真实持仓、新闻源 API key 和通知 webhook 都放在 GitHub Secrets，使用 GitHub Actions 定时运行，避免把敏感信息留在非本人电脑。详细部署说明见 [docs/us-stock-agent-deployment.md](docs/us-stock-agent-deployment.md)，微信机器人说明见 [docs/wechat-bot.md](docs/wechat-bot.md)。

## 文档入口

核心业务逻辑、数据流、评分规则、guardrail 和回测假设见 [docs/principle.md](docs/principle.md)。
