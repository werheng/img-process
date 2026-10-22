"""图片增强处理 API 模块。

提供单张和批量图片处理接口，基于 OpenCV 实现色彩保持的图像增强。
"""

import base64
from pathlib import Path

from flask import Blueprint, request, jsonify
from loguru import logger
from core.response import ok, fail, ApiError
from utils.file_utils import cleanup_temp_file, generate_temp_filename

img_adjust_bp = Blueprint("img_adjust", __name__, url_prefix="/api/img-adjust")

# 上传接口测试性配置：仅允许图片常见扩展名，单文件 ≤ 10MB
_ALLOWED_UPLOAD_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff"}
_MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


def _safe_display_name(filename):
    """清洗用户上传的显示文件名：去路径分隔符，防止路径穿越。"""
    if not filename:
        return "unnamed"
    # 仅取 basename，去掉任何目录片段（Windows 反斜杠 + POSIX 正斜杠）
    name = filename.replace("\\", "/").split("/")[-1].strip()
    # 去掉控制字符和引号，避免后续作为 JSON 字段或日志输出时产生歧义
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '"\'')
    return name[:255] or "unnamed"


def _get_img_service():
    from services.img_adjust_service import ImageAdjustService
    return ImageAdjustService()


@img_adjust_bp.route("/process", methods=["POST"])
def process_image():
    """单张图片处理接口。

    请求体 JSON 格式：
    {
        "image_url": "https://example.com/input.png",
        "brightness": 0,
        "contrast": 0.9,
        "reduce_overexpose": false,
        "threshold": 220,
        "use_clahe": true,
        "gamma": 0.9,
        "denoise": 10
    }
    """
    data = request.get_json(silent=True) or {}
    image_url = data.get("image_url")

    if not image_url:
        raise ApiError("image_url 参数不能为空", code=400, http_status=400)

    service = _get_img_service()
    params = service._build_params(data)

    logger.info(f"[img-adjust] 开始处理图片: {image_url}, params={params}")

    try:
        result = service.process_single(image_url, params)
        return ok(
            data=result,
            message="图片处理成功",
        )
    except RuntimeError as e:
        return fail(message=str(e), code=500, http_status=500)
    except Exception as e:
        logger.exception(f"[img-adjust] 处理异常: {e}")
        return fail(message=f"图片处理异常：{e}", code=500, http_status=500)


@img_adjust_bp.route("/process/batch", methods=["POST"])
def process_batch_images():
    """批量图片处理接口。

    请求体 JSON 格式：
    {
        "image_urls": [
            "https://example.com/a.png",
            "https://example.com/b.jpg"
        ],
        "brightness": 0,
        "contrast": 0.9,
        "reduce_overexpose": false,
        "threshold": 220,
        "use_clahe": true,
        "gamma": 0.9,
        "denoise": 10
    }
    """
    data = request.get_json(silent=True) or {}
    image_urls = data.get("image_urls")

    if not image_urls or not isinstance(image_urls, list):
        raise ApiError("image_urls 参数不能为空且必须为数组", code=400, http_status=400)

    if len(image_urls) > 100:
        raise ApiError("单次批量处理最多支持 100 张图片", code=400, http_status=400)

    service = _get_img_service()
    params = service._build_params(data)

    logger.info(f"[img-adjust] 批量处理开始，共 {len(image_urls)} 张, params={params}")

    try:
        result = service.process_batch(image_urls, params)
        return ok(
            data=result,
            message=f"批量处理完成：成功 {result['success']} 张，失败 {result['failed']} 张",
        )
    except Exception as e:
        logger.exception(f"[img-adjust] 批量处理异常: {e}")
        return fail(message=f"批量处理异常：{e}", code=500, http_status=500)

@img_adjust_bp.route("/upload", methods=["POST"])
def upload_file():
    """图片上传并处理接口（使用临时文件，处理完成后自动删除，仅返回 base64）。

    请求格式：multipart/form-data
      - 文件字段名 `file`（必填）
      - 可选表单字段（与 /process 相同）：
        brightness, contrast, reduce_overexpose, threshold, use_clahe, gamma, denoise
        缺省使用默认值（见 ImageAdjustService._build_params）
    安全约束：
      - 仅允许图片常见扩展名（png/jpg/jpeg/bmp/gif/webp/tiff）
      - 单文件 ≤ 10MB
      - 临时文件名服务端生成（uuid + 原始扩展名），避免路径穿越与覆盖
      - 原始文件名仅作为 file_name 元数据返回，不用于路径拼接

    处理流程：接收文件 -> 写入临时文件 -> OpenCV 增强处理 -> 读取产物转 base64 -> 删除临时文件
      - 输入和输出临时文件在处理完成后均自动清理
      - 响应仅包含 base64 编码的图像数据和基本状态信息
    """
    if "file" not in request.files:
        raise ApiError("缺少文件字段 'file'", code=400, http_status=400)

    file = request.files["file"]
    if not file or not file.filename:
        raise ApiError("文件内容为空", code=400, http_status=400)

    # 扩展名白名单校验（取原始扩展名用于业务限制判断，不用于存储路径）
    original_ext = Path(file.filename).suffix.lower()
    if original_ext not in _ALLOWED_UPLOAD_EXTS:
        raise ApiError(
            f"不允许的文件类型: {original_ext or '(无扩展名)'}，"
            f"仅支持 {sorted(_ALLOWED_UPLOAD_EXTS)}",
            code=400, http_status=400,
        )

    # 大小校验（read 后检查，避免超大文件占满磁盘）
    content = file.read()
    if len(content) == 0:
        raise ApiError("文件内容为空", code=400, http_status=400)
    if len(content) > _MAX_UPLOAD_SIZE:
        raise ApiError(
            f"文件过大（{len(content)} 字节），上限 {_MAX_UPLOAD_SIZE} 字节（10MB）",
            code=400, http_status=400,
        )

    display_name = _safe_display_name(file.filename)

    # 从表单取处理参数（与 /process 一致，缺省走默认值）
    service = _get_img_service()
    form = request.form.to_dict()
    params = service._build_params(form)

    # 使用临时文件：输入和输出均生成在 TEMP_DIR 下，处理完成后自动删除
    input_path = generate_temp_filename(suffix=original_ext)
    output_path = generate_temp_filename(suffix=".jpg")

    logger.info(
        f"[img-adjust] 图片上传并处理: display_name={display_name}, "
        f"params={params}"
    )

    try:
        input_path.write_bytes(content)
        result = service.process_local(str(input_path), params, output_path=output_path)
        # 读取处理后的图片文件，使用 base64 编码返回
        image_base64 = base64.b64encode(output_path.read_bytes()).decode("utf-8")
        size_bytes = result["size_bytes"]
    except Exception as e:
        logger.exception(f"[img-adjust] 上传图片处理失败: {e}")
        return fail(message=f"图片处理失败：{e}", code=500, http_status=500)
    finally:
        # 无论成功或失败，都清理临时文件
        cleanup_temp_file(input_path)
        cleanup_temp_file(output_path)

    logger.info(
        f"[img-adjust] 图片处理成功: display_name={display_name}, "
        f"size={size_bytes}"
    )

    return ok(
        data={
            "processing": result["processing"],
            "file_name": display_name,
            "ext": original_ext,
            "size_bytes": size_bytes,
            "image_base64": image_base64,
        },
        message="图片上传并处理成功",
    )


@img_adjust_bp.route("/upload-url", methods=["POST"])
def upload_file_resp_url():
    """图片上传并处理接口（返回文件 URL）。

    请求格式：multipart/form-data
      - 文件字段名 `file`（必填）
      - 可选表单字段（与 /process 相同）：
        brightness, contrast, reduce_overexpose, threshold, use_clahe, gamma, denoise
        缺省使用默认值（见 ImageAdjustService._build_params）
    安全约束：
      - 仅允许图片常见扩展名（png/jpg/jpeg/bmp/gif/webp/tiff）
      - 单文件 ≤ 10MB
      - 临时文件名服务端生成（uuid + 原始扩展名），避免路径穿越与覆盖
      - 原始文件名仅作为 file_name 元数据返回，不用于路径拼接

    处理流程：接收文件 -> 写入临时文件 -> OpenCV 增强处理 -> 上传 minio -> 删除临时文件
      - 输入和输出临时文件在处理完成后均自动清理
      - 响应包含文件访问 URL 和基本状态信息
    """
    if "file" not in request.files:
        raise ApiError("缺少文件字段 'file'", code=400, http_status=400)

    file = request.files["file"]
    if not file or not file.filename:
        raise ApiError("文件内容为空", code=400, http_status=400)

    # 扩展名白名单校验（取原始扩展名用于业务限制判断，不用于存储路径）
    original_ext = Path(file.filename).suffix.lower()
    if original_ext not in _ALLOWED_UPLOAD_EXTS:
        raise ApiError(
            f"不允许的文件类型: {original_ext or '(无扩展名)'}，"
            f"仅支持 {sorted(_ALLOWED_UPLOAD_EXTS)}",
            code=400, http_status=400,
        )

    # 大小校验（read 后检查，避免超大文件占满磁盘）
    content = file.read()
    if len(content) == 0:
        raise ApiError("文件内容为空", code=400, http_status=400)
    if len(content) > _MAX_UPLOAD_SIZE:
        raise ApiError(
            f"文件过大（{len(content)} 字节），上限 {_MAX_UPLOAD_SIZE} 字节（10MB）",
            code=400, http_status=400,
        )

    display_name = _safe_display_name(file.filename)

    # 从表单取处理参数（与 /process 一致，缺省走默认值）
    service = _get_img_service()
    form = request.form.to_dict()
    params = service._build_params(form)

    # 使用临时文件：输入和输出均生成在 TEMP_DIR 下，处理完成后自动删除
    input_path = generate_temp_filename(suffix=original_ext)
    output_path = generate_temp_filename(suffix=".jpg")

    logger.info(
        f"[img-adjust] 图片上传并处理(URL模式): display_name={display_name}, "
        f"params={params}"
    )

    try:
        input_path.write_bytes(content)
        result = service.process_local(str(input_path), params, output_path=output_path)
        # 上传处理结果到 MinIO，获取访问 URL
        object_name, public_url = service.file_service.upload_file(str(output_path))
        if not object_name:
            raise RuntimeError("MinIO 上传失败")
        size_bytes = result["size_bytes"]
    except RuntimeError as e:
        logger.exception(f"[img-adjust] 上传图片处理失败: {e}")
        return fail(message=str(e), code=500, http_status=500)
    except Exception as e:
        logger.exception(f"[img-adjust] 上传图片处理失败: {e}")
        return fail(message=f"图片处理失败：{e}", code=500, http_status=500)
    finally:
        # 无论成功或失败，都清理临时文件
        cleanup_temp_file(input_path)
        cleanup_temp_file(output_path)

    logger.info(
        f"[img-adjust] 图片处理成功(URL模式): display_name={display_name}, "
        f"object_name={object_name}, size={size_bytes}"
    )

    return ok(
        data={
            "processing": result["processing"],
            "file_name": display_name,
            "size_bytes": size_bytes,
            "object_name": object_name,
            "public_url": public_url,
        },
        message="图片上传并处理成功",
    )


@img_adjust_bp.route("/health", methods=["GET"])
def health():
    """图片处理服务健康检查。"""
    return ok(data={"status": "ok"}, message="图片处理服务运行正常")

