# 美股持仓 Agent 远端部署指南

## 部署目标

本 agent 的目标是在非本机环境中定时生成美股持仓日报和周报。推荐部署到 GitHub 私有仓库，通过 GitHub Actions 定时运行，通过 Secrets/Variables 注入持仓、新闻源和通知配置。

## 必填配置

`PORTFOLIO_JSON` 存放真实持仓，推荐放在 GitHub Secrets。如果只是测试，也可以临时放在 Repository Variables。

```json
{
  "currency": "USD",
  "cash": 4.66,
  "risk_profile": "aggressive",
  "holdings": [
    {"symbol": "MRVL", "quantity": 1, "cost_basis": null, "target_weight": null},
    {"symbol": "NVDA", "quantity": 18, "cost_basis": null, "target_weight": null},
    {"symbol": "QQQ", "quantity": 2.7365, "cost_basis": null, "target_weight": null},
    {"symbol": "SPCX", "quantity": 13, "cost_basis": null, "target_weight": null},
    {"symbol": "SPY", "quantity": 3, "cost_basis": null, "target_weight": null},
    {"symbol": "TSLA", "quantity": 8, "cost_basis": null, "target_weight": null}
  ]
}
```

## 可选配置

新闻源后续可配置 `SERPAPI_API_KEY`、`TAVILY_API_KEY`、`BRAVE_API_KEY` 或自定义 `NEWS_API_KEY`。当前代码只检测配置状态，后续接入付费新闻源时在 `us_stock_agent/news.py` 新增 provider。

## 定时规则

`.github/workflows/us-stock-report.yml` 默认北京时间周二到周六 08:30 生成日报，对应前一美股交易日收盘后；北京时间周六 09:00 生成周报。workflow 也支持手动触发，`report_type` 可选 `daily` 或 `weekly`。

## 输出与审计

workflow 会把 JSON 报告打印到日志，并上传到 `us-stock-report` artifact。报告中的 `report_markdown` 是最终可读报告，外层 JSON 保留 `ok`、`source_api`、`warnings`、`errors` 等机器可读状态。

## 风控边界

动作分层是研究标签，不是自动交易指令。`add_candidate` 必须通过数据质量与触发条件 guardrail；如果行情质量不足、新闻源缺失、缺少进入区间或失效条件，动作会降级为 `watch`。SPCX 是 ETF/基金代码，不能与私营公司 SpaceX 混用。
