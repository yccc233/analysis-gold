import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta

from utils.logger import get_logger

log = get_logger("notify.email")

CST = timezone(timedelta(hours=8))


def _build_body(decision: dict) -> str:
    stars_str = "★" * decision["stars"] + "☆" * (5 - decision["stars"])
    lines = [
        "黄金基金交易决策报告",
        "",
        f"时间: {decision['timestamp']}",
        f"决策评级: {stars_str} ({decision['stars']}星)",
        f"结论: {decision['conclusion']}",
        "",
        "————————————————",
        "【当前价格】",
        f"  人民币价格: {decision['current_price_cny_g']:.2f} 元/克",
        f"  美元价格: {decision['current_price_usd_oz']:.2f} USD/盎司",
        f"  汇率 USD/CNY: {decision['usd_cny']:.4f}",
        "",
    ]

    if decision.get("stats_7d"):
        s = decision["stats_7d"]
        lines.extend([
            "【7日统计】",
            f"  均价: {s['avg']} 元/克 | 最高: {s['high']} | 最低: {s['low']}",
            f"  波动率: {s['volatility']} | 涨跌幅: {s['change_pct']}%",
            "",
        ])

    if decision.get("stats_30d"):
        s = decision["stats_30d"]
        lines.extend([
            "【30日统计】",
            f"  均价: {s['avg']} 元/克 | 最高: {s['high']} | 最低: {s['low']}",
            f"  波动率: {s['volatility']} | 涨跌幅: {s['change_pct']}%",
            "",
        ])

    lines.extend([
        f"  趋势形态: {decision.get('trend', '')}",
        f"  支撑位: {decision.get('support', '')} 元/克 | 压力位: {decision.get('resistance', '')} 元/克",
        "",
        "————————————————",
        "【数据支撑】",
    ])
    for r in decision.get("data_reasons", []):
        lines.append(f"  · {r}")

    lines.extend(["", "【调研支撑】"])
    for r in decision.get("research_reasons", []):
        lines.append(f"  · {r}")

    if decision.get("analysis_summary"):
        lines.extend(["", "————————————————", "【综合分析摘要】", decision["analysis_summary"]])

    return "\n".join(lines)


def send_decision_email(decision: dict) -> bool:
    """当评级 > 3星时发送邮件。返回是否发送成功。"""
    if decision["stars"] <= 3:
        log.info("stars=%d, skip email", decision["stars"])
        return False

    smtp_host = os.getenv("SMTP_HOST", "smtp.qq.com")
    try:
        smtp_port = int(os.getenv("SMTP_PORT", "465"))
    except ValueError:
        log.warning("SMTP_PORT 值无效，使用默认端口 465")
        smtp_port = 465
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    notify_to = os.getenv("NOTIFY_TO", "")

    if not all([smtp_user, smtp_password, notify_to]):
        log.error("邮件配置不完整，跳过发送 (SMTP_USER/SMTP_PASSWORD/NOTIFY_TO)")
        return False

    recipients = [addr.strip() for addr in notify_to.split(",") if addr.strip()]
    if not recipients:
        log.error("NOTIFY_TO 解析后无有效收件人")
        return False

    stars_str = "★" * decision["stars"]
    now_str = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    subject = f"黄金基金决策提醒-{now_str}-{stars_str}"

    body = _build_body(decision)

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = ", ".join(recipients)

    try:
        log.info("连接 SMTP %s:%d ...", smtp_host, smtp_port)
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, recipients, msg.as_string())
        log.info("邮件发送成功: %s -> %s", subject, ", ".join(recipients))
        return True
    except Exception as exc:
        log.error("邮件发送失败: %s", exc)
        return False
