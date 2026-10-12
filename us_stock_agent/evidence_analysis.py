"""将结构化证据交给模型分析，再校验引用、覆盖范围和数字。

模型输出只追加到不可变规则报告，价格、盈亏和动作不由模型重写。引用校验只保证
来源存在，不能证明模型的因果解释正确，因此分析始终标为推断并列出反向证据。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .research_context import DIMENSIONS

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
        if not isinstance(item, dict):
            raise ValueError("分析条目必须是对象。")
        symbol = item["symbol"]
        if not isinstance(symbol, str) or symbol not in evidence or symbol in seen:
            raise ValueError("分析存在未知或重复股票代码。")
        seen.add(symbol)
        source = evidence[symbol]
        v2 = source.get("framework", {}).get("version") == "evidence_research_v2"
        expected_fields = _FIELDS | {"dimensions", "opinion_reviews"} if v2 else _FIELDS
        if set(item) != expected_fields:
            raise ValueError("分析条目不符合六维 dimensions 契约。" if v2 else "分析条目字段不符合契约。")
        allowed_ids = {entry["id"] for entry in source.values() if isinstance(entry, dict) and "id" in entry}
        allowed_ids.update(entry["id"] for entry in source.get("news", []))
        allowed_ids.update(entry["id"] for entry in source.get("social", {}).get("posts", []))
        allowed_ids.update(entry["id"] for entry in source.get("social", {}).get("leads", []))
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
        if v2:
            lines.extend(_render_v2_sections(item, source, allowed_numbers))
        lines.append(f"- 依据：{', '.join(ids)}")
        for news in source.get("news", []):
            if news["id"] in ids and str(news.get("url", "")).startswith("https://"):
                lines.append(f"  - [{news['id']}]({news['url']})（搜索线索，未核验全文）")
    if seen != set(evidence):
        raise ValueError("分析未覆盖本次全部持仓。")
    lines.extend(_render_social_source_list(evidence))
    return "\n".join(lines)


def _numbers(text: str) -> list[str]:
    """归一化数字用于拒绝无来源价格；此检查不替代语义核验。"""
    return re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))


def _render_v2_sections(item: dict, source: dict, allowed_numbers: set[str]) -> list[str]:
    """强制六维覆盖与逐原帖复核，观点来源由程序渲染。"""
    dimensions = item.get("dimensions")
    if not isinstance(dimensions, dict) or set(dimensions) != set(DIMENSIONS):
        raise ValueError("分析必须完整覆盖六维 dimensions。")
    lines = []
    for key, label in DIMENSIONS.items():
        value = _validate_short_text(dimensions[key], allowed_numbers)
        lines.append(f"- {label}：{value}")
    posts = {post["id"]:post for post in source.get("social", {}).get("posts", [])}
    reviews = item.get("opinion_reviews")
    if not isinstance(reviews, list):
        raise ValueError("opinion_reviews 必须为列表。")
    seen = set()
    for review in reviews:
        if not isinstance(review, dict) or set(review) != {"source_id", "stance", "reason"}:
            raise ValueError("博主观点复核字段不完整。")
        ref = review["source_id"]
        if ref not in posts or ref in seen or review["stance"] not in {"支持", "部分支持", "不支持", "待核实"}:
            raise ValueError("博主复核引用、立场或去重不符合契约。")
        seen.add(ref)
        post = posts[ref]
        reason = _validate_short_text(review["reason"], allowed_numbers)
        when = post.get("published_at") or f"{post.get('published_label')}（观察于 {post.get('observed_at')}，无精确发布时间）"
        lines.append(f"- 博主复核 / {post['author']['name']}：{review['stance']}；{reason}")
        lines.append(f"- 来源：[{ref}]({post['url']})；发布时间 {when}；原帖或转录可读不等于金融主张已核验。")
    if seen != set(posts):
        raise ValueError("未逐条覆盖本次可用的博主原帖。")
    if not posts:
        lines.append("- 博主原帖覆盖：本次未取得可用的近期原帖；不能推断作者未发帖或没有分歧。")
    return lines


def _validate_short_text(value: Any, allowed_numbers: set[str]) -> str:
    """校验维度和观点解释的文本、数字与外链边界。"""
    if not isinstance(value, str) or not value.strip() or len(value) > 600:
        raise ValueError("维度或观点复核必须为非空短文本。")
    if set(_numbers(value)) - allowed_numbers or re.search(r"https?://|<[^>]*>", value):
        raise ValueError("维度或观点复核含无来源数字、外链或 HTML。")
    return value.strip()


def _render_social_source_list(evidence: dict) -> list[str]:
    """跨股票去重展示作者原帖摘要，保留发布时间与核验边界。"""
    unique = {}
    for source in evidence.values():
        for post in source.get("social", {}).get("posts", []):
            unique[post["url"]] = post
    if not unique:
        return []
    lines = ["", "## 本次参考的博主原帖", "",
             "原帖已读或用户提供只证明观点出处；其中的财务数字、持仓和业绩仍需独立核验，重合叙事不重复增加可信度。"]
    for url, post in unique.items():
        when = post.get("published_at") or f"{post.get('published_label')}（观察于 {post.get('observed_at')}，未获得精确发布时间）"
        lines.append(f"- [{post['author']['name']}]({url})：{post['text']}；发布时间 {when}。")
    return lines
