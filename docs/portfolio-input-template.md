# 持仓信息填写模板

## 使用方式

把下面的“给 AI 的提示词”复制给任何能看截图或表格的 AI，再附上你的券商持仓截图、导出的 CSV 或手工输入的持仓列表。AI 的任务只做格式转换，不做投资判断。拿到输出后，把 `PORTFOLIO_JSON` 的完整 JSON 填到 GitHub Secrets 或后续一键配置脚本里。

## 给 AI 的提示词

```text
你是一个严谨的数据整理助手。请根据我提供的美股持仓截图、表格或文字，把信息整理成 Stock-EGON 使用的 PORTFOLIO_JSON。

只输出一个 JSON 对象，不要输出解释、Markdown、代码块或多余文字。

字段要求：
1. currency 固定填 "USD"，除非我明确说不是美元账户。
2. cash 填账户现金余额，如果看不到现金余额就填 0。
3. risk_profile 只能是 "conservative"、"balanced"、"aggressive" 三选一；如果我没有说明风险偏好，默认填 "aggressive"。
4. holdings 是数组，每个持仓包含 symbol、quantity、cost_basis、target_weight。
5. symbol 使用美股 ticker，大写，不要包含交易所后缀，例如 AAPL、MSFT、VOO、IWM。
6. quantity 使用数字，允许小数。
7. cost_basis 如果截图里看不到持仓成本或平均成本，填 null。
8. target_weight 如果我没有明确给目标权重，填 null。
9. 不要把当日盈亏、市值、涨跌幅、名称、交易所、币种文字写进 holdings。
10. 如果截图里出现没有公开 ticker 的私营公司，请不要凭公司名编造股票代码；只有截图中明确给出 ticker 时才写入。

请严格输出如下结构：
{
  "currency": "USD",
  "cash": 0,
  "risk_profile": "aggressive",
  "holdings": [
    {"symbol": "AAPL", "quantity": 3, "cost_basis": null, "target_weight": null}
  ]
}
```

## 你可以附给 AI 的补充信息

如果截图里字段不完整，可以在提示词后补充这些信息：

```text
我的现金余额是：____ USD。
我的风险偏好是：aggressive。
如果某只股票数量看不清，请先列出你无法确认的 ticker，不要猜。
```

## 输出验收规则

AI 输出必须是一个合法 JSON 对象，不能带 Markdown 代码块。`holdings` 里每个 `symbol` 必须是大写 ticker，`quantity` 必须是数字，缺失的 `cost_basis` 和 `target_weight` 必须用 `null`。如果 AI 从截图中无法确认某个数量，应要求重新提供更清晰截图，而不是猜一个值。

## 示例输出

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
