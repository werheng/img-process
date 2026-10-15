"""loguru 日志初始化模块。

统一提供控制台 + 文件双输出，文件自动按大小轮转、按天数保留、zip 压缩。
业务模块直接使用：from loguru import logger
"""

import sys
from pathlib import Path

from loguru import logger

from config import LOG_FILE, LOG_LEVEL, LOG_ROTATION, LOG_RETENTION

# 全局标志：防止重复初始化
_configured = False

# 控制台/文件统一格式
_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)
_FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"


def setup_logger():
    """初始化 loguru 日志（控制台 + 文件）。可重复调用，仅首次生效。"""
    global _configured
    if _configured:
        return

    # 确保日志目录存在
    log_file_path = Path(LOG_FILE)
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    # 移除默认处理器
    logger.remove()

    # 控制台输出
    logger.add(
        sink=sys.stdout,
        level=LOG_LEVEL,
        format=_CONSOLE_FORMAT,
        colorize=True,
    )

    # 文件输出：按大小轮转 + 按天数保留 + zip 压缩
    logger.add(
        sink=LOG_FILE,
        level=LOG_LEVEL,
        format=_FILE_FORMAT,
        rotation=LOG_ROTATION,
        retention=LOG_RETENTION,
        compression="zip",
        enqueue=True,
    )

    _configured = True
    logger.info(f"日志初始化完成：level={LOG_LEVEL}, file={LOG_FILE}")


def get_logger():
    """获取已配置的 logger 实例。"""
    setup_logger()
    return logger