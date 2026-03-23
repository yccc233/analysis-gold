import json
import math
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from itertools import cycle

from utils.logger import get_logger

log = get_logger("analysis.decision")

CST = timezone(timedelta(hours=8))

SYSTEM_PROMPT = """你是一位专业的黄金基金交易分析师。你的任务是根据给定的价格数据和调研信息，对当前黄金市场的投资时机进行综合分析，并给出1-5星的决策评级。

【分析维度】
你必须从以下三个维度进行综合分析：

1. **技术面分析**：
   - 当前价格与7日/30日均线的偏离程度
   - 价格在支撑位和压力位之间的位置
   - 历史波动率评估
   - 近期价格趋势形态（上行/下行/震荡）

2. **基本面分析**：
   - 美元指数走势对黄金的影响（美元走强利空黄金，美元走弱利好黄金）
   - 国际局势（地缘政治风险、央行购金、宏观经济环境）
   - 实际利率变化（实际利率上升利空黄金，下降利好黄金）

3. **市场情绪与机构观点**：
   - 权威机构的最新观点和预测
   - 市场情绪指标
   - 资金流向信号

【决策评级标准】
- ★★★★★（5星，强烈推荐买入）：多个维度一致看多，技术面低位+基本面利好+市场情绪积极
- ★★★★☆（4星，推荐买入）：两个维度支持买入，风险收益比良好
- ★★★☆☆（3星，建议观望）：多空因素交织，方向不明朗
- ★★☆☆☆（2星，不推荐操作）：利空因素多于利多，建议谨慎
- ★☆☆☆☆（1星，极不推荐操作）：技术面高位+基本面利空+市场情绪悲观

【输出要求】
你必须返回严格有效的JSON格式，不要包含任何其他文字：
{
  "stars": 数字1-5,
  "conclusion": "结论文字（10字以内）",
  "analysis_summary": "综合分析摘要（100-200字，涵盖三个维度的核心判断）",
  "data_reasons": ["数据支撑理由1", "数据支撑理由2", ...],
  "research_reasons": ["调研支撑理由1", "调研支撑理由2", ...]
}"""

USER_PROMPT_TEMPLATE = """【当前价格数据】
- 当前时间：{timestamp}
- 黄金现货价格：{current_price_cny} 元/克（{current_price_usd} USD/盎司）
- 汇率：USD/CNY {usd_cny}

【7日统计数据】
{stats_7d}

【30日统计数据】
{stats_30d}

【趋势与位置分析】
- 近期趋势：{trend}
- 支撑位：{support} 元/克
- 压力位：{resistance} 元/克

【权威调研摘要】
{research_summary}

请基于以上数据，从技术面、基本面、市场情绪三个维度进行综合分析，返回JSON格式的决策结果。"""


def _calc_stats(history: list[dict], days: int) -> dict | None:
    cutoff = int(datetime.now(timezone.utc).timestamp()) - days * 86400
    prices = [r["price_cny_g"] for r in history if r["ts_utc"] >= cutoff]
    if not prices:
        return None
    avg = sum(prices) / len(prices)
    high = max(prices)
    low = min(prices)
    variance = sum((p - avg) ** 2 for p in prices) / len(prices)
    volatility = math.sqrt(variance)
    first, last = prices[0], prices[-1]
    change_pct = ((last - first) / first) * 100 if first else 0
    return {
        "avg": round(avg, 2),
        "high": round(high, 2),
        "low": round(low, 2),
        "volatility": round(volatility, 2),
        "change_pct": round(change_pct, 2),
        "count": len(prices),
    }


def _detect_trend(history: list[dict]) -> str:
    if len(history) < 3:
        return "数据不足"
    prices = [r["price_cny_g"] for r in history]
    n = len(prices)
    mid = n // 2
    first_half_avg = sum(prices[:mid]) / mid
    second_half_avg = sum(prices[mid:]) / (n - mid)
    diff_pct = ((second_half_avg - first_half_avg) / first_half_avg) * 100
    if diff_pct > 1.0:
        return "上行趋势"
    elif diff_pct < -1.0:
        return "下行趋势"
    return "震荡整理"


def _calc_support_resistance(history: list[dict]) -> dict:
    prices = [r["price_cny_g"] for r in history]
    if not prices:
        return {"support": 0, "resistance": 0}
    sorted_p = sorted(prices)
    n = len(sorted_p)
    if n < 10:
        return {"support": round(sorted_p[0], 2), "resistance": round(sorted_p[-1], 2)}
    support = sorted_p[max(0, int(n * 0.1))]
    resistance = sorted_p[min(n - 1, int(n * 0.9))]
    return {"support": round(support, 2), "resistance": round(resistance, 2)}


def _build_prompt(
    timestamp: str,
    current_price_cny: float,
    current_price_usd: float,
    usd_cny: float,
    stats_7d: dict | None,
    stats_30d: dict | None,
    trend: str,
    support: float,
    resistance: float,
    research: dict,
) -> tuple[str, str]:
    stats_7d_text = (
        f"均价: {stats_7d['avg']} 元/克, 最高: {stats_7d['high']} 元/克, "
        f"最低: {stats_7d['low']} 元/克, 波动率: {stats_7d['volatility']}, "
        f"涨跌幅: {stats_7d['change_pct']}%, 数据量: {stats_7d['count']}条"
        if stats_7d
        else "数据不足"
    )
    stats_30d_text = (
        f"均价: {stats_30d['avg']} 元/克, 最高: {stats_30d['high']} 元/克, "
        f"最低: {stats_30d['low']} 元/克, 波动率: {stats_30d['volatility']}, "
        f"涨跌幅: {stats_30d['change_pct']}%, 数据量: {stats_30d['count']}条"
        if stats_30d
        else "数据不足"
    )

    if research.get("success") and research.get("answers"):
        research_parts = []
        for ans in research.get("answers", []):
            q = ans.get("query", "")
            a = ans.get("answer", "")
            research_parts.append(f"[{q}] {a[:300]}")
        research_summary = "\n".join(research_parts)
    else:
        research_summary = "调研数据获取失败，仅基于价格数据分析"

    user_prompt = USER_PROMPT_TEMPLATE.format(
        timestamp=timestamp,
        current_price_cny=current_price_cny,
        current_price_usd=current_price_usd,
        usd_cny=usd_cny,
        stats_7d=stats_7d_text,
        stats_30d=stats_30d_text,
        trend=trend,
        support=support,
        resistance=resistance,
        research_summary=research_summary,
    )
    return SYSTEM_PROMPT, user_prompt


def _get_llm_config() -> tuple[str, str, list]:
    api_url = os.getenv("LLM_API_URL", "")
    api_key = os.getenv("LLM_API_KEY", "")
    raw_models = os.getenv("LLM_MODELS", "deepseek-chat")
    models = [m.strip() for m in raw_models.split(",") if m.strip()]
    if not api_url or not api_key:
        raise RuntimeError("Missing LLM_API_URL or LLM_API_KEY in .env")
    if not models:
        models = ["deepseek-chat"]
    return api_url, api_key, models


def _call_llm(system_prompt: str, user_prompt: str, model: str) -> str:
    api_url, api_key, _ = _get_llm_config()

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 2048,
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "gtm-analysis/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            usage = result.get("usage", {})
            finish_reason = result["choices"][0].get("finish_reason", "")
            log.debug("LLM usage: %s, finish_reason: %s", usage, finish_reason)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        log.error("LLM API HTTP %d: %s %s", exc.code, exc.reason, body[:300])
        raise

    content = result["choices"][0]["message"]["content"]
    return content.strip()


def _parse_llm_response(raw: str) -> dict:
    # 尝试提取 JSON 代码块或纯 JSON
    for start in ["```json", "```"]:
        if start in raw:
            idx = raw.find(start) + len(start)
            end = raw.find("```", idx)
            if end != -1:
                raw = raw[idx:end].strip()
                break

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.error("LLM 响应JSON解析失败: %s | raw: %s", exc, raw[:200])
        raise

    stars = int(data.get("stars", 3))
    stars = max(1, min(5, stars))
    return {
        "stars": stars,
        "conclusion": str(data.get("conclusion", "建议观望")),
        "analysis_summary": str(data.get("analysis_summary", "")),
        "data_reasons": data.get("data_reasons", []),
        "research_reasons": data.get("research_reasons", []),
    }


def _fallback_decision(
    current_price: float,
    stats_7d: dict | None,
    stats_30d: dict | None,
    trend: str,
    support_resistance: dict,
) -> tuple[int, list[str], list[str]]:
    """降级规则打分（LLM调用失败时的兜底）"""
    score = 0
    data_reasons = []
    research_reasons = ["【降级说明】LLM调用失败，采用规则打分"]

    insufficient = False
    if stats_7d and stats_7d["count"] < 3:
        data_reasons.append(f"历史数据不足(仅{stats_7d['count']}条)，分析结果可信度低")
        insufficient = True

    if stats_7d:
        if current_price < stats_7d["avg"]:
            diff = ((stats_7d["avg"] - current_price) / stats_7d["avg"]) * 100
            score += 2
            data_reasons.append(f"当前价 {current_price} 元/克 低于7日均价 {stats_7d['avg']} 元/克 ({diff:.1f}%)")
        else:
            diff = ((current_price - stats_7d["avg"]) / stats_7d["avg"]) * 100
            score -= 1
            data_reasons.append(f"当前价 {current_price} 元/克 高于7日均价 {stats_7d['avg']} 元/克 (+{diff:.1f}%)")

    if stats_30d:
        if current_price < stats_30d["avg"]:
            diff = ((stats_30d["avg"] - current_price) / stats_30d["avg"]) * 100
            score += 2
            data_reasons.append(f"当前价低于30日均价 {stats_30d['avg']} 元/克 ({diff:.1f}%)")
        else:
            diff = ((current_price - stats_30d["avg"]) / stats_30d["avg"]) * 100
            score -= 1
            data_reasons.append(f"当前价高于30日均价 {stats_30d['avg']} 元/克 (+{diff:.1f}%)")

    sr = support_resistance
    if sr["support"] and current_price <= sr["support"] * 1.02:
        score += 2
        data_reasons.append(f"当前价接近支撑位 {sr['support']} 元/克，存在反弹机会")
    elif sr["resistance"] and current_price >= sr["resistance"] * 0.98:
        score -= 2
        data_reasons.append(f"当前价接近压力位 {sr['resistance']} 元/克，上涨空间有限")

    if trend == "下行趋势":
        score -= 1
        data_reasons.append("近期整体呈下行趋势")
    elif trend == "上行趋势":
        score += 1
        data_reasons.append("近期整体呈上行趋势")
    elif trend == "数据不足":
        data_reasons.append("历史数据不足，无法判断趋势")
    else:
        data_reasons.append("近期价格震荡整理")

    if stats_7d and stats_7d["volatility"] > stats_7d["avg"] * 0.02:
        score -= 1
        data_reasons.append(f"7日波动率较高 ({stats_7d['volatility']:.2f})，风险偏大")

    if insufficient:
        score = min(score, 0)

    if score >= 4:
        stars = 5
    elif score >= 2:
        stars = 4
    elif score >= 0:
        stars = 3
    elif score >= -2:
        stars = 2
    else:
        stars = 1

    conclusions = {
        5: "强烈推荐买入",
        4: "推荐买入",
        3: "建议观望",
        2: "不推荐操作",
        1: "极不推荐操作",
    }
    return stars, data_reasons, research_reasons


def analyze(current_price_data: dict, history: list[dict], research: dict) -> dict:
    current_price = current_price_data["price_cny_g"]
    stats_7d = _calc_stats(history, 7)
    stats_30d = _calc_stats(history, 30)
    trend = _detect_trend(history)
    sr = _calc_support_resistance(history)

    log.info("分析输入: 当前价 %.2f 元/克, 历史数据 %d 条, 趋势: %s", current_price, len(history), trend)
    if stats_7d:
        log.info("7日统计: 均价 %.2f, 最高 %.2f, 最低 %.2f, 波动率 %.2f, 涨跌 %.2f%%, 数据量 %d",
                 stats_7d["avg"], stats_7d["high"], stats_7d["low"],
                 stats_7d["volatility"], stats_7d["change_pct"], stats_7d["count"])
    if stats_30d:
        log.info("30日统计: 均价 %.2f, 最高 %.2f, 最低 %.2f, 波动率 %.2f, 涨跌 %.2f%%, 数据量 %d",
                 stats_30d["avg"], stats_30d["high"], stats_30d["low"],
                 stats_30d["volatility"], stats_30d["change_pct"], stats_30d["count"])
    log.info("支撑位 %.2f / 压力位 %.2f", sr["support"], sr["resistance"])

    timestamp = current_price_data.get("ts_local", "")
    system_prompt, user_prompt = _build_prompt(
        timestamp=timestamp,
        current_price_cny=current_price,
        current_price_usd=current_price_data.get("price_usd_oz", 0),
        usd_cny=current_price_data.get("usd_cny", 0),
        stats_7d=stats_7d,
        stats_30d=stats_30d,
        trend=trend,
        support=sr["support"],
        resistance=sr["resistance"],
        research=research,
    )

    # 记录完整提示词，供人工复核
    log.info("========== LLM System Prompt ==========\n%s", system_prompt)
    log.info("========== LLM User Prompt ==========\n%s", user_prompt)

    llm_result = None
    try:
        _, _, models = _get_llm_config()
        model_pool = cycle(models)
        selected_model = next(model_pool)
        log.info("调用 LLM 进行综合分析 (model: %s, pool: %s)...", selected_model, models)
        raw = _call_llm(system_prompt, user_prompt, selected_model)
        log.info("LLM 返回原始内容: %s", raw[:500] if raw else "(空响应)")
        log.info("LLM 返回原始内容长度: %d 字符", len(raw))
        llm_result = _parse_llm_response(raw)
        log.info("LLM 分析结果: %d stars — %s", llm_result["stars"], llm_result["conclusion"])
    except Exception as exc:
        log.error("LLM 调用失败，切换降级规则打分: %s", exc)
        stars, data_reasons, research_reasons = _fallback_decision(
            current_price, stats_7d, stats_30d, trend, sr,
        )
        llm_result = {
            "stars": stars,
            "conclusion": {5: "强烈推荐买入", 4: "推荐买入", 3: "建议观望", 2: "不推荐操作", 1: "极不推荐操作"}[stars],
            "analysis_summary": "【系统降级说明】LLM服务不可用，采用规则打分作为兜底方案，分析结果仅供参考。",
            "data_reasons": data_reasons,
            "research_reasons": research_reasons,
        }

    result = {
        "timestamp": timestamp,
        "current_price_cny_g": current_price,
        "current_price_usd_oz": current_price_data.get("price_usd_oz", 0),
        "usd_cny": current_price_data.get("usd_cny", 0),
        "stats_7d": stats_7d,
        "stats_30d": stats_30d,
        "trend": trend,
        "support": sr["support"],
        "resistance": sr["resistance"],
        "stars": llm_result["stars"],
        "conclusion": llm_result["conclusion"],
        "analysis_summary": llm_result.get("analysis_summary", ""),
        "data_reasons": llm_result.get("data_reasons", []),
        "research_reasons": llm_result.get("research_reasons", []),
    }

    log.info("decision: %d stars — %s (price: %.2f CNY/g)", result["stars"], result["conclusion"], current_price)
    return result
