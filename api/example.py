"""示例业务模块。

新建业务时的参考模板：
1. 在 api/ 下新建 blue_xxx.py，定义蓝图与路由
2. 在 api/__init__.py 中导出
3. 在 services/ 下实现业务服务类
"""

import time

from flask import Blueprint, request
from loguru import logger

from core.response import ok, fail, ApiError

example_bp = Blueprint("example", __name__, url_prefix="/api/example")


@example_bp.route("/health", methods=["GET"])
def health():
    """示例健康检查。"""
    return ok(data={"time": time.time()}, message="示例服务运行正常")


@example_bp.route("/echo", methods=["POST"])
def echo():
    """示例回显接口：演示统一响应、request_id、耗时统计。"""
    start = time.time()
    data = request.get_json(silent=True) or {}
    rid = data.get("request_id") or request.args.get("request_id")

    text = data.get("text")
    if not text:
        raise ApiError("text 参数不能为空", code=400, http_status=400)

    logger.info(f"[示例] request_id={rid} - echo: {text}")

    return ok(
        data={
            "echo": text,
            "cost_time": round(time.time() - start, 3),
        },
        message="回显成功",
        rid=rid,
    )


@example_bp.route("/error", methods=["GET"])
def error_demo():
    """示例错误接口：演示统一错误处理。"""
    raise ApiError("这是业务异常示例", code=400, http_status=400)