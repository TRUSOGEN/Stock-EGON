"""研究上下文：六维框架、市场基准、指定作者观点与时效校验。

博主原帖与其中金融主张分开标注：读到原帖并不代表其数字已被独立核实。云端搜索
只能提供待核验线索，浏览器已读摘要保留观察时间并自动过期，不借用个人登录态。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit
from typing import Any, Mapping

import numpy as np
import pandas as pd
import requests

DIMENSIONS = {
    "market": "市场环境与相对表现", "fundamentals": "经营质量与估值",
    "catalysts": "事件催化与兑现条件", "technical": "价格行为与失效条件",
    "social": "指定博主观点与分歧", "portfolio": "组合风险与情景复核",
}
_DEFAULT_SOURCES = Path(__file__).resolve().parents[1] / "config" / "social-sources.json"


def build_research_contexts(provider: Any, symbols: list[str], *, now: datetime | None = None) -> tuple[dict, list[str]]:
    """收集可验证的基准与聚合财务字段；单源失败不会冒充零值。"""
    timestamp = now or datetime.now(timezone.utc)
    benchmarks, warnings = {}, []
    if callable(getattr(provider, "fetch_company_facts", None)):
        for benchmark in ("SPY", "QQQ"):
            try:
                quote = provider.fetch_snapshot([benchmark])[benchmark]
                history = provider.fetch_history(benchmark)
                benchmarks[benchmark] = {
                    "price": quote.price, "data_time": quote.data_time,
                    "return_20_sessions": _return(history, 20), "return_60_sessions": _return(history, 60),
                    "source": quote.source,
                }
            except Exception as exc:
                warnings.append(f"市场基准 {benchmark} 不可用（{type(exc).__name__}）。")
    results = {}
    for symbol in symbols:
        facts = {"status": "not_available", "reason": "provider_does_not_supply_fundamentals"}
        if callable(getattr(provider, "fetch_company_facts", None)):
            try:
                facts = provider.fetch_company_facts(symbol)
            except Exception as exc:
                facts = {"status": "fetch_failed", "reason": type(exc).__name__}
                warnings.append(f"{symbol} 基本面不可用（{type(exc).__name__}）。")
        history = provider.fetch_history(symbol)
        own_return = _return(history, 20)
        market = {"id": f"{symbol}:market", "benchmarks": benchmarks,
                  "analysis_as_of": timestamp.isoformat(), "return_20_sessions": own_return,
                  "volatility_20_sessions_annualized": _volatility(history),
                  "relative_return_20_sessions": {
                      key: round(own_return - value["return_20_sessions"], 6)
                      if own_return is not None and value["return_20_sessions"] is not None else None
                      for key, value in benchmarks.items()},
                  "macro_rates_and_breadth": "not_supplied_by_quote_provider"}
        results[symbol] = {"market": market,
                           "fundamentals": {"id": f"{symbol}:fundamentals", **facts},
                           "framework": {"id": f"{symbol}:framework", "version": "evidence_research_v2",
                                         "dimensions": DIMENSIONS, "analysis_as_of": timestamp.isoformat(),
                                         "comparison_history": "not_available", "social_popularity_is_accuracy": False}}
    return results, warnings


def collect_social_opinions(symbols: list[str], *, env: Mapping[str, str], now: datetime | None = None,
                            get: Any = None) -> tuple[dict, list[str]]:
    """加载指定作者原帖摘要，并按作者查询新线索；过去七天之外的内容不当作近期观点。"""
    timestamp = now or datetime.now(timezone.utc)
    raw = env.get("SOCIAL_OPINIONS_JSON", "").strip()
    payload = json.loads(raw) if raw else json.loads(_DEFAULT_SOURCES.read_text()) if _DEFAULT_SOURCES.exists() else {}
    authors = payload.get("authors", [])
    posts = payload.get("posts", [])
    if not isinstance(authors, list) or not isinstance(posts, list):
        raise ValueError("社交观点配置必须包含 authors 和 posts 列表。")
    by_id = {}
    for author in authors:
        if author.get("platform") not in {"x", "xiaohongshu"} or not author.get("id") or not author.get("name"):
            raise ValueError("作者配置缺少有效平台、id 或名称。")
        if author["id"] in by_id:
            raise ValueError("作者 id 重复。")
        _check_url(author["profile_url"], author["platform"])
        by_id[author["id"]] = author
    results = {symbol: {"id": f"{symbol}:social", "status": "no_recent_posts" if authors else "not_configured",
                        "authors": authors, "posts": [], "leads": [], "analysis_as_of": timestamp.isoformat(),
                        "claims_verified": False} for symbol in symbols}
    warnings, seen = [], set()
    for post in posts:
        author = by_id.get(post.get("author_id"))
        if author is None:
            raise ValueError("观点引用了未配置作者。")
        url = _check_url(post["url"], author["platform"])
        if author["platform"] == "x" and urlsplit(url).path.split('/')[1].lower() != author.get("handle", "").lower():
            raise ValueError("X 原帖链接与作者账号不匹配。")
        if post.get("observed_at") and datetime.fromisoformat(post["observed_at"].replace("Z", "+00:00")) > timestamp:
            raise ValueError("观点观察时间不能在未来。")
        latest_possible = _post_latest_time(post)
        if latest_possible > timestamp or latest_possible < timestamp - timedelta(days=7):
            warnings.append(f"{author['name']} 的缓存观点已过期或日期在未来，未计入近期观点。")
            continue
        text = str(post.get("text", "")).strip()
        if not text or post.get("content_kind") not in {"browser_read_summary", "user_transcription"}:
            raise ValueError("观点需要非空摘要及明确的 content_kind。")
        if url in seen:
            continue
        seen.add(url)
        for symbol in symbols:
            if symbol not in post.get("symbols", []) and "*" not in post.get("symbols", []):
                continue
            item = {**post, "id": f"{symbol}:social:post:{len(results[symbol]['posts'])}", "url": url,
                    "author": author, "verification": "original_page_read_claims_unverified"
                    if post["content_kind"] == "browser_read_summary" else "user_provided_not_independently_verified"}
            results[symbol]["posts"].append(item)
            results[symbol]["status"] = "recent_opinions_available"
    search_key = env.get("SERPAPI_API_KEY", "").strip() or env.get("SERPAPI_API_KEYS", "").split(',')[0].strip()
    if authors and search_key and env.get("SOCIAL_SEARCH_ENABLED", "true").lower() != "false":
        for author in authors:
            try:
                rows = _search_author(author, symbols, search_key, get=get or requests.get)
                for row in rows:
                    for symbol in symbols:
                        if not re.search(rf"\b{re.escape(symbol)}\b", row["text"], re.I) and symbol not in {"SPY", "QQQ"}:
                            continue
                        results[symbol]["leads"].append({**row, "id": f"{symbol}:social:lead:{len(results[symbol]['leads'])}",
                                                         "requested_author": author["name"],
                                                         "verification": "search_excerpt_author_and_date_unverified"})
            except Exception as exc:
                warnings.append(f"{author['name']} 的社交搜索失败（{type(exc).__name__}），本次未宣称覆盖其新帖。")
    if authors:
        warnings.append("社交搜索索引可能漏帖；原帖已读不代表其金融主张已核验，未获取新帖不代表作者没有发表。")
    return results, warnings


def _search_author(author: dict, symbols: list[str], key: str, *, get: Any) -> list[dict]:
    """限定作者与平台做搜索；搜索摘要只作为线索，不宣称原帖身份已确认。"""
    if author["platform"] == "x":
        query = f"site:x.com/{author['handle']}/status ({' OR '.join(symbols)} OR market OR stocks)"
    else:
        query = f"site:xiaohongshu.com \"{author['name']}\" ({' OR '.join(symbols)} OR 美股 OR 特斯拉 OR SpaceX)"
    response = get("https://serpapi.com/search.json", params={"engine":"google", "q":query,
                   "api_key":key, "num":3, "tbs":"qdr:w"}, timeout=10)
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise ValueError("社交搜索返回 API 错误。")
    items = []
    for row in payload.get("organic_results", [])[:3]:
        url = row.get("link", "")
        try:
            url = _check_url(url, author["platform"])
        except ValueError:
            continue
        if author["platform"] == "x" and not urlsplit(url).path.lower().startswith(f"/{author['handle'].lower()}/status/"):
            continue
        items.append({"url":url, "text":f"{row.get('title', '')} {row.get('snippet', '')}".strip(),
                      "published_label":row.get("date"), "content_kind":"search_excerpt"})
    return items


def _post_latest_time(post: dict) -> datetime:
    """用精确日期或浏览时的相对日龄判断过期，不伪造小红书的精确发布时间。"""
    if post.get("published_at"):
        value = datetime.fromisoformat(str(post["published_at"]).replace('Z','+00:00'))
        if value.tzinfo is None:
            raise ValueError("观点发布时间必须带时区。")
        return value
    label = str(post.get("published_label", ""))
    match = re.fullmatch(r"(\d+)天前", label)
    if not match or not post.get("observed_at"):
        raise ValueError("观点缺少可校验日期；相对日期需要 observed_at。")
    observed = datetime.fromisoformat(post["observed_at"].replace('Z','+00:00'))
    if observed.tzinfo is None:
        raise ValueError("观点观察时间必须带时区。")
    return observed - timedelta(days=max(int(match.group(1))-1, 0))


def _check_url(value: str, platform: str) -> str:
    """只接收相应平台 HTTPS 链接，并剔除分享 token 与跟踪参数。"""
    parsed = urlsplit(value)
    domains = {"x":{"x.com","www.x.com","twitter.com","www.twitter.com"},
               "xiaohongshu":{"xiaohongshu.com","www.xiaohongshu.com"}}
    if parsed.scheme != "https" or parsed.netloc not in domains[platform]:
        raise ValueError("观点链接与平台不匹配。")
    return urlunsplit((parsed.scheme,parsed.netloc,parsed.path,'',''))


def _return(history: pd.DataFrame, sessions: int) -> float | None:
    """计算完整交易日收盘价格收益，不包含股息再投资。"""
    if len(history) <= sessions:
        return None
    return round(float(history['close'].iloc[-1] / history['close'].iloc[-sessions-1] - 1), 6)


def _volatility(history: pd.DataFrame) -> float | None:
    """计算最近二十个日收益的年化样本标准差。"""
    if len(history) < 21:
        return None
    value = history['close'].pct_change().tail(20).std(ddof=1)*np.sqrt(252)
    return round(float(value),6) if np.isfinite(value) else None
