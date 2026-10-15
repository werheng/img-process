"""Flask 服务基础框架应用工厂。

新服务用法：
    from app import create_app
    app = create_app("development")

或直接：
    python app.py            # 开发模式
    gunicorn app:app -w 4    # 生产模式
"""

import os
import sys

from flask import Flask
from loguru import logger

from config import config_map
from core import setup_logger
from core.response import register_error_handlers

# 初始化日志
setup_logger()


def create_app(config_name: str = None) -> Flask:
    """创建 Flask 应用实例。

    Args:
        config_name: 配置名称（development/production），默认从环境变量 FLASK_ENV 读取，否则 default

    Returns:
        Flask 应用实例
    """
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "default")

    app = Flask(__name__)

    # 加载配置
    config_class = config_map[config_name]
    app.config.from_object(config_class)

    # 注册全局异常处理
    register_error_handlers(app)

    # 注册业务蓝图（在 api/__init__.py 中统一导出）
    from api import __all__ as blueprint_names
    for bp_name in blueprint_names:
        bp = getattr(__import__("api", fromlist=[bp_name]), bp_name)
        app.register_blueprint(bp)
        logger.info(f"已注册蓝图：{bp.name}")

    # 根路由
    @app.route("/")
    def index():
        return {
            "service": config_class.SERVICE_NAME,
            "version": config_class.SERVICE_VERSION,
            "endpoints": {
                "health": "/api/health",
                "example": "/api/example/health",
                "img_adjust_process": "/api/img-adjust/process",
                "img_adjust_batch": "/api/img-adjust/process/batch",
            },
        }

    return app


# 默认应用实例
app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "15000"))
    app.run(host="0.0.0.0", port=port, debug=config_map[os.environ.get("FLASK_ENV", "default")].DEBUG)