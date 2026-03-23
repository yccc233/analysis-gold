import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from gold.config import DEFAULT_GRAMS_PER_UNIT
from gold.db import insert_price
from utils.logger import get_logger

log = get_logger("gold.api")


def fetch_xau_usd(api_key: str) -> float:
    url = "https://app.goldapi.net/api/price/xau/usd"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "gold-price-poller/1.0",
            "x-api-key": api_key,
        },
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                return float(payload["price"])
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            log.error("GoldAPI HTTP %d: %s %s", exc.code, exc.reason, body[:200])
            raise
        except Exception as exc:
            log.warning("GoldAPI 超时/异常 (attempt %d/3): %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(2)
            else:
                log.error("GoldAPI 3次尝试全部失败")
                raise


def fetch_usd_cny_rate() -> float:
    url = "https://open.er-api.com/v6/latest/USD"
    req = urllib.request.Request(url, headers={"User-Agent": "gold-price-poller/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                rates = payload.get("rates", {})
                return float(rates["CNY"])
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            log.error("FX API HTTP %d: %s %s", exc.code, exc.reason, body[:200])
            raise
        except Exception as exc:
            log.warning("FX API 超时/异常 (attempt %d/3): %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(2)
            else:
                log.error("FX API 3次尝试全部失败")
                raise


def fetch_and_store(
    conn,
    api_key: str,
    grams_per_unit: float = DEFAULT_GRAMS_PER_UNIT,
) -> dict:
    """获取实时金价并写入数据库，返回本次数据。金价与汇率同步查询。"""
    # 同步获取 FX 汇率（每次实时查询，消除时间差）
    usd_cny = fetch_usd_cny_rate()
    log.info("FX rate: USD/CNY %.4f", usd_cny)

    price_usd_oz = round(fetch_xau_usd(api_key), 2)
    price_cny_g = round((price_usd_oz * usd_cny) / grams_per_unit, 2)
    usd_cny = round(usd_cny, 4)
    ts_local = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    ts_utc = int(datetime.now(timezone.utc).timestamp())

    insert_price(conn, ts_utc, ts_local, price_cny_g, price_usd_oz, usd_cny)

    result = {
        "ts_utc": ts_utc,
        "ts_local": ts_local,
        "price_cny_g": price_cny_g,
        "price_usd_oz": price_usd_oz,
        "usd_cny": usd_cny,
    }
    log.info("price fetched: CNY/g %.2f  USD/oz %.2f  USD/CNY %.4f",
             result["price_cny_g"], result["price_usd_oz"], result["usd_cny"])
    return result
