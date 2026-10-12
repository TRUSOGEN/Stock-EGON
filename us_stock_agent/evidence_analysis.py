"""将结构化证据交给模型分析，再校验引用、覆盖范围和数字。

模型输出只追加到不可变规则报告，价格、盈亏和动作不由模型重写。引用校验只保证
来源存在，不能证明模型的因果解释正确，因此分析始终标为推断并列出反向证据。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_FIELDS = {"symbol", "thesis", "counter_evidence", "uncertainty", "next_check", "evidence_ids"}
_TEXT_FIELDS = ("thesis", "counter_evidence", "uncertainty", "next_check")
_PROMPT = Path(__file__).with_name("prompts") / "evidence_analysis.md"


def build_analysis_payload(evidence: dict[str, Any], *, model: str, max_tokens: int) -> dict[str, Any]:
    """构造 JSON 模式分析请求；搜索文本只作为证据数据。"""
    return {
        "model": model, "stream": True, "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _PROMPT.read_text(encoding="utf-8")},
            {"role": "user", "content": json.dumps(evidence, ensure_ascii=False, allow_nan=False)},
        ],
    }


def validate_and_render_analysis(text: str, evidence: dict[str, Any]) -> str:
    """验证结构、逐票引用与数字后生成独立分析区块。"""
    payload = json.loads(text)
    if not isinstance(payload, dict) or set(payload) != {"positions"} or not isinstance(payload["positions"], list):
        raise ValueError("分析响应必须是仅含 positions 列表的 JSON 对象。")
    seen = set()
    lines = ["## AI 证据分析（推断，需人工复核）", "",
             "以下分析不改变上面的程序行情、规则动作或风险计算；引用通过校验不等于因果关系已证实。"]
    for item in payload["positions"]:
        if not isinstance(item, dict) or set(item) != _FIELDS:
            raise ValueError("分析条目字段不符合契约。")
        symbol = item["symbol"]
        if not isinstance(symbol, str) or symbol not in evidence or symbol in seen:
            raise ValueError("分析存在未知或重复股票代码。")
        seen.add(symbol)
        source = evidence[symbol]
        allowed_ids = {entry["id"] for entry in source.values() if isinstance(entry, dict) and "id" in entry}
        allowed_ids.update(entry["id"] for entry in source.get("news", []))
        ids = item["evidence_ids"]
        if not isinstance(ids, list) or not ids or any(not isinstance(ref, str) or ref not in allowed_ids for ref in ids):
            raise ValueError(f"{symbol} 分析引用了缺失或不存在的证据。")
        allowed_numbers = set(_numbers(json.dumps(source, ensure_ascii=False)))
        lines.extend(["", f"### {symbol} 证据复核"])
        for field, label in zip(_TEXT_FIELDS, ("判断与机制", "反向证据", "不确定性", "下一步核验")):
            value = item[field]
            if not isinstance(value, str) or not value.strip() or len(value) > 1200:
                raise ValueError(f"{symbol} 的 {field} 必须为非空短文本。")
            if set(_numbers(value)) - allowed_numbers:
                raise ValueError(f"{symbol} 分析出现输入证据以外的数字。")
            if re.search(r"https?://|<[^>]*>", value):
                raise ValueError("分析文本不得添加外部链接或 HTML。")
            lines.append(f"- {label}：{value.strip()}")
        lines.append(f"- 依据：{', '.join(ids)}")
        for news in source.get("news", []):
            if news["id"] in ids and str(news.get("url", "")).startswith("https://"):
                lines.append(f"  - [{news['id']}]({news['url']})（搜索线索，未核验全文）")
    if seen != set(evidence):
        raise ValueError("分析未覆盖本次全部持仓。")
    return "\n".join(lines)


def _numbers(text: str) -> list[str]:
    """归一化数字用于拒绝无来源价格；此检查不替代语义核验。"""
    return re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))
