# Stock-EGON

Stock-EGON 是一个股票研究辅助项目，当前包含两部分：基于 AKShare 的 A 股量化分析 CLI，以及面向真实美股持仓的日报、周报、邮件推送工作流。项目用于研究复盘和风险提示，不提供投资建议、交易指令或自动交易。

## 你要做的三件事

第一步，把仓库保留在 GitHub 私有仓库里，然后打开 `Actions` 页面启用 `US Stock Portfolio Report` workflow。这个 workflow 会在北京时间周二到周六 08:30 生成日报，在北京时间周六 09:00 生成周报，也可以手动运行。

第二步，在 GitHub 仓库的 `Settings` -> `Secrets and variables` -> `Actions` 页面，停留在 `Secrets` 标签页，不要切到 `Variables`。点击 `New repository secret`，`Name` 填 `PORTFOLIO_JSON`，`Secret` 填下面“最小可用配置”里的完整 JSON。真实持仓不要提交到仓库，也不要放到 Variables。

第三步，如果要邮件推送，QQ 邮箱推荐只在同一个 `Secrets` 标签页新增 `EMAIL_ADDRESS` 和 `EMAIL_AUTH_CODE`。`EMAIL_ADDRESS` 填你的 QQ 邮箱，`EMAIL_AUTH_CODE` 填 QQ 邮箱生成的 SMTP 授权码，不要填网页登录密码。其他邮箱仍可使用完整 SMTP 配置。

如果你不想手工写 `PORTFOLIO_JSON`，可以把 [docs/portfolio-input-template.md](docs/portfolio-input-template.md) 里的提示词发给 AI，再附上持仓截图或表格，让 AI 只负责整理出可复制的 JSON。

如果你想一次性填持仓、邮箱、LLM 投研助理和新闻源，可以直接打开网页版配置向导 [https://trusogen.github.io/Stock-EGON/config-wizard.html](https://trusogen.github.io/Stock-EGON/config-wizard.html)。如果你在本地仓库里操作，也可以继续打开 [docs/config-wizard.html](docs/config-wizard.html)。这个页面会在浏览器本地生成一段一键终端脚本，右侧只保留最重要的那一段命令。生成后的脚本可以直接复制到本机终端执行，macOS 默认 zsh 或 bash 都可以；如果终端提示没有登录 GitHub CLI，先运行 `gh auth login`。向导里也支持填写成本价，并可默认开启“每只股票一张价格和成交量报价图内嵌到邮件正文”。

## AI API 和复用边界

当前美股日报和周报的核心判断仍然来自 Python 规则引擎：读取持仓，拉取行情和可选新闻源，按趋势、动量、组合风险和 guardrail 生成报告。LLM 投研助理是可选增强层，只在配置 key 后把规则报告改写成更适合邮件阅读的中文解释。所以别人复用这个项目时，不会用你的 Codex，也不需要你的 OpenAI key。

别人要复用时，应 fork 仓库到自己的 GitHub 账号，并在自己的仓库 Secrets 里配置自己的 `PORTFOLIO_JSON`、邮箱 SMTP、新闻源 key 和可选 LLM key。真实持仓、邮箱授权码、新闻源 key 和 LLM key 都不应该写进代码。

GitHub Actions 不能复用你本机的 Codex 登录态。需要 LLM 增强时，火山方舟应配置 `ARK_API_KEY` 和 `ARK_MODEL`，DeepSeek 官方接口应配置 `DEEPSEEK_API_KEY`，其他 OpenAI-compatible 服务可配置 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`。也兼容 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL` 这类常见命名。详细说明见 [docs/llm-config-guide.md](docs/llm-config-guide.md)。

## 暂停服务

最快暂停方式是在 GitHub 仓库 `Actions` 页面点进 `US Stock Portfolio Report`，右上角选择 `Disable workflow`。这样定时任务和手动任务都会停。

如果只想临时暂停但保留 workflow，可在 `Settings` -> `Secrets and variables` -> `Actions` -> `Variables` 里新增或修改 `REPORT_ENABLED=false`。要恢复时把它改成 `true`，或者删掉这个 Variable。

## GitHub Secrets 照填表

在 `Actions secrets and variables` 页面里，只使用 `Repository secrets`。点击 `New repository secret` 后按下表填写：

| Name | Secret 填什么 | 是否必填 | 放在哪里 |
|---|---|---:|---|
| `PORTFOLIO_JSON` | 你的完整持仓 JSON | 是 | Secrets |
| `EMAIL_ADDRESS` | QQ 邮箱地址，例如 `you@qq.com` | QQ 邮件推荐必填 | Secrets |
| `EMAIL_AUTH_CODE` | QQ 邮箱 SMTP 授权码 | QQ 邮件推荐必填 | Secrets |
| `EMAIL_SMTP_HOST` | SMTP 服务器，例如 `smtp.gmail.com` | 其他邮箱可选 | Secrets |
| `EMAIL_SMTP_PORT` | SMTP 端口，通常是 `587` | 其他邮箱可选 | Secrets |
| `EMAIL_USERNAME` | 发件邮箱账号 | 其他邮箱可选 | Secrets |
| `EMAIL_PASSWORD` | 发件邮箱应用专用密码 | 其他邮箱可选 | Secrets |
| `EMAIL_FROM` | 发件邮箱地址 | 其他邮箱可选 | Secrets |
| `EMAIL_TO` | 收件邮箱地址，多个用逗号分隔 | 其他邮箱可选 | Secrets |
| `EMAIL_INCLUDE_CHARTS` | 是否把每只股票一张价格和成交量报价图内嵌到邮件正文，推荐填 `true` | 否 | Secrets 或 Variables |
| `ARK_API_KEY` | 火山方舟 API key | 火山方舟必填 | Secrets |
| `ARK_MODEL` | 火山方舟 model 或接入点 ID | 火山方舟必填 | Secrets 或 Variables |
| `ARK_BASE_URL` | 火山方舟 base URL，默认 `https://ark.cn-beijing.volces.com/api/v3` | 火山方舟可选 | Secrets 或 Variables |
| `DEEPSEEK_API_KEY` | DeepSeek API key，自动使用 `https://api.deepseek.com` 和 `deepseek-chat` | LLM 可选 | Secrets |
| `LLM_API_KEY` | 通用 OpenAI-compatible API key | LLM 可选 | Secrets |
| `LLM_BASE_URL` | 通用 OpenAI-compatible base URL | LLM 可选 | Secrets 或 Variables |
| `LLM_MODEL` | 通用模型名，例如 `deepseek-chat` | LLM 可选 | Secrets 或 Variables |
| `OPENAI_API_KEY` | 兼容 OpenAI 命名的 API key | LLM 可选 | Secrets |
| `OPENAI_BASE_URL` | 兼容 OpenAI 命名的 base URL | LLM 可选 | Secrets 或 Variables |
| `OPENAI_MODEL` | 兼容 OpenAI 命名的模型名 | LLM 可选 | Secrets 或 Variables |
| `BRAVE_API_KEY` | Brave Search key，默认优先推荐 | 否 | Secrets |
| `TAVILY_API_KEY` | Tavily 新闻搜索 key，默认优先推荐 | 否 | Secrets |
| `SERPAPI_API_KEY` | SerpAPI 新闻搜索 key | 否 | Secrets |
| `ALPHA_VANTAGE_API_KEY` | Alpha Vantage News & Sentiment key，适合补充 ticker 新闻但成本通常更高 | 否 | Secrets |

不要把持仓、邮箱密码和 API key 填到 `Variables`，因为 Variables 是明文配置；Secrets 才是加密配置。`REPORT_ENABLED=false` 这种非敏感开关可以放到 Variables。

LLM 增强层只改写报告，不负责创造交易结论。未配置 LLM key 时会跳过增强并发送原始规则报告；已配置 LLM key 但请求失败时，邮件任务会失败并在 Actions 日志中暴露错误，避免你以为收到的是 AI 增强报告。

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

手动运行方式：进入 GitHub `Actions` -> `US Stock Portfolio Report` -> `Run workflow`，`report_type` 选择 `daily` 或 `weekly`。运行完成后，可以在日志里看到 JSON，也可以在 `Artifacts` 下载 `us-stock-report`；配置了邮件 SMTP 后，收件邮箱会收到纯文本报告。

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

运行配置预检：

```bash
python scripts/preflight.py
```

通过邮件发送已生成的美股报告：

```bash
EMAIL_ADDRESS="you@qq.com" EMAIL_AUTH_CODE="smtp-auth-code" \
python scripts/send_email_report.py --report-file reports/us-daily-report.json
```

通过邮件发送报告并在正文内嵌每只股票的价格和成交量报价图：

```bash
EMAIL_ADDRESS="you@qq.com" EMAIL_AUTH_CODE="smtp-auth-code" EMAIL_INCLUDE_CHARTS="true" \
python scripts/send_email_report.py --report-file reports/us-daily-report.json
```

使用 DeepSeek 增强后再发邮件：

```bash
DEEPSEEK_API_KEY="your-deepseek-key" \
EMAIL_ADDRESS="you@qq.com" EMAIL_AUTH_CODE="smtp-auth-code" \
python scripts/send_email_report.py --report-file reports/us-daily-report.json
```

使用通用 OpenAI-compatible 服务增强后再发邮件：

```bash
LLM_API_KEY="your-provider-key" LLM_BASE_URL="https://api.example.com/v1" LLM_MODEL="provider/model" \
EMAIL_ADDRESS="you@qq.com" EMAIL_AUTH_CODE="smtp-auth-code" \
python scripts/send_email_report.py --report-file reports/us-daily-report.json
```

使用完整 SMTP 配置发送已生成的美股报告：

```bash
EMAIL_SMTP_HOST="smtp.example.com" EMAIL_SMTP_PORT="587" \
EMAIL_USERNAME="bot@example.com" EMAIL_PASSWORD="app-password" \
EMAIL_FROM="bot@example.com" EMAIL_TO="you@example.com" \
python scripts/send_email_report.py --report-file reports/us-daily-report.json
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

核心业务逻辑、数据流、评分规则、guardrail 和回测假设见 [docs/principle.md](docs/principle.md)。LLM 投研助理配置见 [docs/llm-config-guide.md](docs/llm-config-guide.md)。零基础 GitHub 配置教程见 [docs/github-actions-beginner.md](docs/github-actions-beginner.md)。
