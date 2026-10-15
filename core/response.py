"""统一响应封装与全局异常处理。

所有接口统一返回：
{
    "code": 200,
    "request_id": "...",
    "success": true,
    "data": {...},
    "message": "..."
}
"""

import time
import uuid

from flask import jsonify, request
from loguru import logger


class ApiError(Exception):
    """业务异常：携带 HTTP 状态码与错误码。"""

    def __init__(self, message: str, code: int = 500, http_status: int = None):
        """
        Args:
            message: 错误描述
            code: 业务错误码（默认 500）
            http_status: HTTP 状态码（默认与 code 一致）
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status if http_status is not None else (code if 100 <= code < 600 else 500)


def _new_request_id() -> str:
    """生成请求 ID。"""
    return str(uuid.uuid4())[:8]


def _request_id() -> str:
    """优先使用请求体/查询参数中的 request_id，否则自动生成。"""
    rid = None
    if request.is_json:
        rid = request.get_json(silent=True).get("request_id") if request.get_json(silent=True) else None
    if not rid:
        rid = request.args.get("request_id")
    return rid or _new_request_id()


def ok(data=None, message: str = "成功", code: int = 200, rid: str = None):
    """成功响应。"""
    return jsonify({
        "code": code,
        "request_id": rid or _new_request_id(),
        "success": True,
        "data": data if data is not None else {},
        "message": message,
    })


def fail(message: str, code: int = 400, data=None, http_status: int = None, rid: str = None):
    """失败响应。"""
    status = http_status if http_status is not None else code
    if not (100 <= status < 600):
        status = 500
    return jsonify({
        "code": code,
        "request_id": rid or _new_request_id(),
        "success": False,
        "data": data if data is not None else {},
        "message": message,
    }), status


def error_response(e: Exception, rid: str = None):
    """将 ApiError / 未知异常转为统一失败响应。

    Args:
        e: 异常对象
        rid: 请求 ID

    Returns:
        Flask 响应
    """
    if isinstance(e, ApiError):
        logger.warning(f"[接口异常] request_id={rid} - 业务错误：{e.message}")
        return fail(
            message=e.message,
            code=e.code,
            http_status=e.http_status,
            rid=rid,
        )

    logger.exception(f"[接口异常] request_id={rid} - 未捕获异常：{e}")
    return fail(
        message=f"服务器内部错误：{e}",
        code=500,
        http_status=500,
        rid=rid,
    )


def register_error_handlers(app):
    """注册全局异常处理。

    Args:
        app: Flask 应用实例
    """
    @app.errorhandler(ApiError)
    def handle_api_error(e):
        return error_response(e, rid=_request_id())

    @app.errorhandler(404)
    def handle_404(e):
        return fail(message="接口不存在", code=404, http_status=404, rid=_request_id())

    @app.errorhandler(405)
    def handle_405(e):
        return fail(message="请求方法不允许", code=405, http_status=405, rid=_request_id())

    @app.errorhandler(500)
    def handle_500(e):
        logger.exception(f"[服务器错误] {e}")
        return fail(message="服务器内部错误", code=500, http_status=500, rid=_request_id())