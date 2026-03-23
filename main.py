import os
import signal
import sys
import time

# 确保项目根目录在 sys.path 中
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from utils.dotenv import load_dotenv
from utils.logger import get_logger
from gold.db import init_db, get_history
from gold.api import fetch_and_store
from research.tavily import run_research
from analysis.decision import analyze
from notify.email import send_decision_email

log = get_logger("main")

DEFAULT_INTERVAL = 3600  # 1小时

_shutdown = False


def _handle_signal(sig, frame):
    global _shutdown
    _shutdown = True


def run_once(conn, api_key: str) -> dict | None:
    """执行一次完整流程：调研 → 获取价格 → 分析决策 → 邮件通知。"""

    # 1. 调研
    log.info("=" * 50)
    log.info("开始执行决策流程")
    log.info("步骤1: 黄金趋势调研")
    research = run_research()
    if not research.get("success"):
        log.warning("调研失败，将仅基于价格数据分析")

    # 2. 获取价格
    log.info("步骤2: 获取实时金价")
    try:
        current = fetch_and_store(conn, api_key)
    except Exception as exc:
        log.error("金价获取失败: %s", exc)
        return None

    # 3. 历史数据 + 分析决策
    log.info("步骤3: 波动分析与决策评级")
    history = get_history(conn, days=30)
    decision = analyze(current, history, research)

    stars_str = "★" * decision["stars"] + "☆" * (5 - decision["stars"])
    log.info("决策结果: %s %s — 当前价 %.2f 元/克",
             stars_str, decision["conclusion"], decision["current_price_cny_g"])

    # 4. 邮件通知 (>3星)
    log.info("步骤4: 邮件通知判断")
    send_decision_email(decision)

    log.info("本轮流程完成")
    return decision


def main() -> int:
    load_dotenv(os.path.join(ROOT_DIR, ".env"))

    api_key = os.getenv("GOLDAPI_KEY")
    if not api_key:
        log.error("Missing GOLDAPI_KEY. Set it in .env file.")
        return 2

    try:
        interval = float(os.getenv("POLL_INTERVAL", str(DEFAULT_INTERVAL)))
    except ValueError:
        log.warning("POLL_INTERVAL 值无效，使用默认值 %ds", DEFAULT_INTERVAL)
        interval = float(DEFAULT_INTERVAL)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    conn = init_db()
    try:
        log.info("黄金基金智能交易辅助决策系统启动 (间隔 %ds)", int(interval))

        while not _shutdown:
            started = time.time()
            try:
                run_once(conn, api_key)
            except Exception as exc:
                log.error("流程异常: %s", exc, exc_info=True)

            elapsed = time.time() - started
            wait = max(0, interval - elapsed)
            # 短轮询等待，以便及时响应中断信号
            while wait > 0 and not _shutdown:
                time.sleep(min(wait, 5))
                wait -= 5
    finally:
        conn.close()
        log.info("数据库连接已关闭")

    log.info("程序正常退出")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
