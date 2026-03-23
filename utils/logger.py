import logging
import os
import sys
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# 固定宽度配置（文件日志使用）
_FILE_MSG_WIDTH = 100


class _FixedWidthFormatter(logging.Formatter):
    """消息区域固定宽度，不足的用空格填充。"""

    def __init__(self, msg_width: int = _FILE_MSG_WIDTH):
        super().__init__(
            fmt="%(asctime)s [%(name)s] %(levelname)s ",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self._msg_width = msg_width

    def format(self, record: logging.LogRecord) -> str:
        prefix = super().format(record)
        # 将消息截断或填充到固定宽度
        msg = str(record.getMessage())
        if len(msg) > self._msg_width:
            msg = msg[: self._msg_width - 3] + "..."
        else:
            msg = msg.ljust(self._msg_width)
        return prefix + msg


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)

    # 控制台：原始格式（不填充）
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(name)s] %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(sh)

    # 文件：消息区域固定宽度
    fh = RotatingFileHandler(
        os.path.join(LOG_DIR, "gtm.log"),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_FixedWidthFormatter())
    logger.addHandler(fh)

    return logger
