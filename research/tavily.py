import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from itertools import cycle

from utils.logger import get_logger

log = get_logger("research.tavily")

CST = timezone(timedelta(hours=8))

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"
MAX_RETRIES = 2


def _get_api_keys() -> list[str]:
    """从环境变量获取 Tavily API Key 列表，支持逗号分隔多个 Key。"""
    raw = os.getenv("TAVILY_API_KEYS", "") or os.getenv("TAVILY_API_KEY", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise RuntimeError("Missing TAVILY_API_KEYS in environment or .env")
    return keys


def _post_json(url: str, payload: dict, timeout: int = 30) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "gtm-research/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _retry_call(func, *args, retries: int = MAX_RETRIES):
    last_exc = None
    for attempt in range(1 + retries):
        try:
            return func(*args)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            last_exc = exc
            log.warning("attempt %d failed: %s", attempt + 1, exc)
            if attempt < retries:
                time.sleep(2)
    raise last_exc


def _build_queries() -> list[str]:
    now = datetime.now(CST)
    ym = now.strftime("%Y年%m月")
    return [
        f"{ym}黄金价格趋势分析 元/克",
        "黄金支撑位压力位 最新 元/克",
        "美元指数与黄金关联 人民币计价",
    ]


def _search(api_key: str, query: str) -> tuple[list[dict], str | None]:
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "advanced",
        "max_results": 5,
        "include_domains": [
            "eastmoney.com", "10jqka.com.cn", "jin10.com",
            "gold.org", "pbc.gov.cn",
        ],
        "include_answer": True,
    }
    resp = _post_json(TAVILY_SEARCH_URL, payload)
    results = []
    for r in resp.get("results", []):
        results.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
            "score": r.get("score", 0),
        })
    answer = resp.get("answer")
    return results, answer


def _extract(api_key: str, urls: list[str]) -> list[dict]:
    if not urls:
        return []
    payload = {
        "api_key": api_key,
        "urls": urls[:3],
    }
    resp = _post_json(TAVILY_EXTRACT_URL, payload)
    extracted = []
    for r in resp.get("results", []):
        extracted.append({
            "url": r.get("url", ""),
            "raw_content": r.get("raw_content", ""),
        })
    return extracted


def run_research() -> dict:
    """
    执行黄金趋势调研，返回结构化结果。
    多个 API Key 轮换使用，每次调用分配不同的 Key，分散月额度消耗。
    失败时返回 {"success": False, "error": ...}。
    """
    try:
        keys = _get_api_keys()
    except RuntimeError as exc:
        log.error(str(exc))
        return {"success": False, "error": str(exc), "items": []}

    log.info("loaded %d Tavily API key(s)", len(keys))
    key_pool = cycle(keys)

    queries = _build_queries()
    all_items = []
    answers = []

    for q in queries:
        api_key = next(key_pool)
        key_suffix = api_key[-6:]
        log.info("searching: %s (key: ...%s)", q, key_suffix)
        try:
            results, answer = _retry_call(_search, api_key, q)
            all_items.extend(results)
            if answer:
                answers.append({"query": q, "answer": answer})
            if len(results) == 0:
                log.warning("search returned 0 results: %s", q)
            else:
                log.info("search OK: %s (%d results)", q, len(results))
        except Exception as exc:
            log.error("search FAIL after retries: %s — %s", q, exc)

    # 爬取得分最高的页面获取详细内容
    top_urls = [item["url"] for item in sorted(all_items, key=lambda x: x["score"], reverse=True)[:3]]
    extracts = []
    if top_urls:
        api_key = next(key_pool)
        key_suffix = api_key[-6:]
        log.info("extracting %d pages (key: ...%s)", len(top_urls), key_suffix)
        try:
            extracts = _retry_call(_extract, api_key, top_urls)
            log.info("extract OK: %d pages", len(extracts))
        except Exception as exc:
            log.error("extract FAIL: %s", exc)

    log.info("调研完成: %d 条搜索结果, %d 个摘要, %d 页正文",
             len(all_items), len(answers), len(extracts))
    return {
        "success": True,
        "timestamp": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"),
        "items": all_items,
        "answers": answers,
        "extracts": extracts,
    }
