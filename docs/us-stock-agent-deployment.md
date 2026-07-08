# 美股持仓 Agent 远端部署指南

## 部署目标

本 agent 的目标是在非本机环境中定时生成美股持仓日报和周报。推荐部署到 GitHub 私有仓库，通过 GitHub Actions 定时运行，通过 Secrets/Variables 注入持仓、新闻源和通知配置。用户日常只需要维护 GitHub Secrets，不需要把真实持仓留在当前电脑。

当前美股 agent 的核心判断不依赖 Codex、OpenAI 或其他 LLM API。它是规则引擎，主要依赖 yfinance 行情、可选新闻搜索 provider、持仓配置和 SMTP 通知。LLM 投研助理是可选增强层，只在配置 key 后把规则报告改写成更适合邮件阅读的中文解释。任何人复用时都应 fork 仓库，并配置自己的 Secrets；不会也不能复用你的 Codex 登录态。

## 必填配置

`PORTFOLIO_JSON` 存放真实持仓，必须放在 GitHub Secrets。路径是 GitHub 仓库页面的 `Settings` -> `Secrets and variables` -> `Actions`。进入页面后停留在 `Secrets` 标签页，找到 `Repository secrets`，点击 `New repository secret`。

照下面填第一个 repository secret：

| 表单字段 | 填写内容 |
|---|---|
| `Name` | `PORTFOLIO_JSON` |
| `Secret` | 完整持仓 JSON，也就是下面示例这种对象 |

不要填到 `Variables`。Variables 是明文配置，不适合真实持仓。

如果不想手工写 JSON，可以复制 [portfolio-input-template.md](portfolio-input-template.md) 里的提示词给 AI，再附上持仓截图或表格，让 AI 输出完整 `PORTFOLIO_JSON`。AI 只做数据整理，不应补充投资判断，也不应猜测看不清的数量。

如果想一次性配置持仓、邮件、LLM 投研助理和新闻源，可以直接打开网页版配置向导 [https://trusogen.github.io/Stock-EGON/config-wizard.html](https://trusogen.github.io/Stock-EGON/config-wizard.html)。如果你是在本地仓库里阅读文档，也可以继续打开 [config-wizard.html](config-wizard.html)。它会在浏览器本地生成一段一键终端脚本，右侧只保留最关键的那一段命令。复制生成的一键脚本后，粘贴到本机终端执行即可，脚本会通过 `gh secret set --repo TRUSOGEN/Stock-EGON -f -` 批量写入 GitHub Secrets。macOS 默认 zsh 或 bash 都可以；如果终端提示 GitHub CLI 未登录，先运行 `gh auth login`。

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

## 可选配置

新闻源推荐优先配置 `BRAVE_API_KEY` 或 `TAVILY_API_KEY`，成本通常比 Alpha Vantage 更友好。也支持 `SERPAPI_API_KEY`、`ALPHA_VANTAGE_API_KEY`，并兼容逗号分隔的 `SERPAPI_API_KEYS`、`TAVILY_API_KEYS`、`BRAVE_API_KEYS`。当前默认顺序是 `brave,tavily,serpapi,alphavantage`；可通过 `NEWS_PROVIDER_ORDER` 调整。报告会把每只持仓的最新标题压缩进市场背景，并把 earnings、SEC、downgrade、Fed、inflation 等关键词映射为粗粒度风险标签。

QQ 邮箱推送推荐只配置 `EMAIL_ADDRESS` 和 `EMAIL_AUTH_CODE`。`EMAIL_ADDRESS` 填 QQ 邮箱地址，`EMAIL_AUTH_CODE` 填 QQ 邮箱生成的 SMTP 授权码。workflow 会自动使用 `smtp.qq.com:587`，发件人和收件人默认都是 `EMAIL_ADDRESS`。这些值都应放在 GitHub Secrets。若希望邮件正文内嵌每只股票的周、月、年三联 K 线图，再额外配置 `EMAIL_INCLUDE_CHARTS=true`。

其他邮箱可继续配置完整 SMTP 字段：`EMAIL_SMTP_HOST`、`EMAIL_SMTP_PORT`、`EMAIL_USERNAME`、`EMAIL_PASSWORD`、`EMAIL_FROM`、`EMAIL_TO`。配置后 workflow 会在生成日报或周报 JSON 后调用 `scripts/send_email_report.py`，把报告整理成更适合邮件阅读的文本和 HTML 正文后发出。Gmail、QQ 邮箱、Outlook 等通常需要应用专用密码，不要填写网页登录密码。

LLM 投研助理可选配置。火山方舟应配置 `ARK_API_KEY` 和 `ARK_MODEL`，默认使用 `https://ark.cn-beijing.volces.com/api/v3`。DeepSeek 官方接口可配置 `DEEPSEEK_API_KEY`，系统会自动使用 `https://api.deepseek.com` 和 `deepseek-chat`。通用 OpenAI-compatible 服务可配置 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`。为了兼容常见项目，也支持 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`。未配置 LLM key 时会跳过增强并发送规则报告；已配置 LLM key 但调用失败时，邮件任务会失败并显示错误，避免假装增强成功。细节见 [llm-config-guide.md](llm-config-guide.md)。

企业微信推送脚本仍保留在 `scripts/send_wechat_report.py`，但默认 workflow 已改为邮件推送。如果后续重新使用企业微信群机器人，可以再配置 `WECHAT_WEBHOOK_URL` 并把 workflow 接回该脚本。

普通企业微信群机器人只支持单向推送，不支持接收你的追问。后续如果要做到“报告发到微信，我直接问它为什么可以买、为什么要卖”，需要增加企业微信应用、公众号或自建 webhook callback 服务，具体边界见 [wechat-bot.md](wechat-bot.md)。

## 定时规则

`.github/workflows/us-stock-report.yml` 默认北京时间周二到周六 08:30 生成日报，对应前一美股交易日收盘后；北京时间周六 09:00 生成周报。workflow 也支持手动触发，`report_type` 可选 `daily` 或 `weekly`。正式生成前会先运行 `scripts/preflight.py`，提早暴露持仓 JSON、邮件、LLM、新闻源和正文图表配置的问题。

## 暂停与恢复

暂停有两种方式。最直接方式是在 GitHub `Actions` 页面进入 `US Stock Portfolio Report`，点击 `Disable workflow`。更细的方式是在 `Settings` -> `Secrets and variables` -> `Actions` -> `Variables` 中新增 `REPORT_ENABLED=false`，workflow 会跳过整个报告任务。恢复时把 `REPORT_ENABLED` 改成 `true` 或删除该变量。

## 手动运行

进入 GitHub `Actions` -> `US Stock Portfolio Report` -> `Run workflow`，`report_type` 选择 `daily` 或 `weekly`。如果 `PORTFOLIO_JSON` 未配置或格式错误，workflow 会失败并在日志里输出 `ok=false` 的错误 JSON。

## 输出与审计

workflow 会把 JSON 报告打印到日志，并上传到 `us-stock-report` artifact。报告中的 `report_markdown` 是规则引擎报告，外层 JSON 保留 `ok`、`source_api`、`warnings`、`errors` 等机器可读状态。邮件推送会输出一个 `send_email_report` JSON，便于确认是已发送、已跳过、SMTP 失败、是否启用了 LLM 增强，以及是否内嵌了 K 线图。

## 风控边界

动作分层是研究标签，不是自动交易指令。`add_candidate` 必须通过数据质量与触发条件 guardrail；如果行情质量不足、新闻源缺失、缺少进入区间或失效条件，动作会降级为 `watch`。没有公开 ticker 的私营公司不能当作股票代码写入持仓；只有券商持仓页明确显示 ticker 时才写入。
