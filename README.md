# Stock-EGON

本项目提供两个研究辅助工具：一个基于 AKShare 的 A 股量化分析 CLI，一个面向美股持仓的日报与周报 agent。工具定位是研究辅助与结构化复盘，不提供投资建议。

## 快速开始

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

## 远端部署建议

本项目已提供 [.github/workflows/us-stock-report.yml](.github/workflows/us-stock-report.yml) 模板。推荐把代码推到 GitHub 私有仓库，在 GitHub Secrets 里配置 `PORTFOLIO_JSON`、新闻源 API key 和通知渠道，使用 GitHub Actions 定时运行，避免把真实持仓和密钥留在非本人电脑。详细部署说明见 [docs/us-stock-agent-deployment.md](docs/us-stock-agent-deployment.md)。

## 文档入口

核心业务逻辑、数据流、评分规则、guardrail 和回测假设见 [docs/principle.md](docs/principle.md)。
