"""图片增强处理服务。

基于 OpenCV 对图片做色彩保持的增强处理（亮度/对比度、过度曝光、
CLAHE 直方图均衡、Gamma 校正、降噪），处理结果上传 MinIO 返回访问 URL。

处理流程：下载远端图片 -> 本地增强处理 -> 上传 MinIO -> 返回 URL。
"""

import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from config import BaseConfig
from services.file_service import FileService
from utils.file_utils import download_file, cleanup_temp_file, generate_temp_filename
from utils.img_adjust import process_image_with_report
from core.response import ApiError


# 图片处理参数默认值与取值范围
_PARAM_DEFAULTS = {
    "brightness": 0,
    "contrast": 0.9,
    "reduce_overexpose": False,
    "threshold": 250,
    "use_clahe": True,
    "gamma": 0.9,
    "denoise": 0,
}


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _as_bool(value):
    """兼容 JSON 布尔值与 multipart 表单中的布尔字符串。"""
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return bool(value)


class ImageAdjustService:
    """图片增强处理服务。"""

    def __init__(self):
        self.file_service = FileService()

    def _build_params(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """解析并校验处理参数，缺失用默认值，越界做钳制。

        mode=auto 时逐图选择方案，忽略手动参数；缺省 mode=manual 保持兼容。
        仅从 data 中提取图片属性参数（brightness/contrast/threshold/gamma/
        denoise/reduce_overexpose/use_clahe），其余字段（如 image_url、
        image_urls、file 等）一律忽略。未传入的图片属性参数使用
        _PARAM_DEFAULTS 中的默认值。
        """
        data = data or {}

        mode = data.get("mode", "manual")
        if mode not in ("auto", "manual"):
            raise ApiError("mode 必须为 manual 或 auto", code=400)
        if mode == "auto":
            return {"mode": "auto"}
        params = {"mode": "manual"}

        brightness = _clamp(float(data.get("brightness", _PARAM_DEFAULTS["brightness"])), -128, 127)
        params["brightness"] = brightness

        contrast = _clamp(float(data.get("contrast", _PARAM_DEFAULTS["contrast"])), 0.5, 2.0)
        params["contrast"] = contrast

        threshold = _clamp(int(data.get("threshold", _PARAM_DEFAULTS["threshold"])), 1, 254)
        params["threshold"] = threshold

        gamma = _clamp(float(data.get("gamma", _PARAM_DEFAULTS["gamma"])), 0.1, 3.0)
        params["gamma"] = gamma

        denoise = data.get("denoise", _PARAM_DEFAULTS["denoise"])
        if denoise is not None and denoise != "":
            denoise = _clamp(int(denoise), 0, 100)
        params["denoise"] = denoise or None

        # 布尔开关：接受 bool / "true" / 1 等
        params["reduce_overexpose"] = _as_bool(data.get("reduce_overexpose", _PARAM_DEFAULTS["reduce_overexpose"]))
        params["use_clahe"] = _as_bool(data.get("use_clahe", _PARAM_DEFAULTS["use_clahe"]))

        return params

    def process_single(self, image_url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理单张远端图片，返回 (object_name, public_url, filename)。

        Args:
            image_url: 远端图片 URL
            params: 处理参数（见 _build_params）

        Returns:
            {"object_name": str, "public_url": str, "filename": str}
        """
        input_path: Optional[Path] = None
        output_path: Optional[Path] = None
        try:
            # 1. 下载
            input_path = download_file(image_url, BaseConfig.TEMP_DIR)
            logger.info(f"[img-adjust] 已下载：{input_path}")

            # 2. 增强处理
            output_path = generate_temp_filename(suffix=".jpg")
            processing = process_image_with_report(str(input_path), str(output_path), **params)
            logger.info(f"[img-adjust] 处理完成：{output_path}")

            # 3. 上传 MinIO
            object_name, public_url = self.file_service.upload_file(str(output_path))
            if not object_name:
                raise RuntimeError("MinIO 上传失败")

            return {
                "object_name": object_name,
                "public_url": public_url,
                "filename": input_path.name,
                "processing": processing,
            }

        finally:
            cleanup_temp_file(input_path)
            cleanup_temp_file(output_path)

    def process_local(self, local_input_path: str, params: Dict[str, Any], output_path: Optional[Path] = None) -> Dict[str, Any]:
        """处理本地图片文件（不依赖远端下载，也不上传 MinIO）。

        输入文件会被增强处理，输出写到 TEMP_DIR/upload 下的 uuid 文件（或指定的 output_path），
        原输入文件保留，由调用方负责生命周期管理。

        Args:
            local_input_path: 输入图片本地路径
            params: 处理参数（见 _build_params）
            output_path: 输出文件路径，默认在 TEMP_DIR/upload 下生成 uuid 文件

        Returns:
            {"output_path": str, "size_bytes": int}

        Raises:
            RuntimeError: 图片处理或写出失败
        """
        input_p = Path(local_input_path)
        if output_path is None:
            out_dir = Path(BaseConfig.TEMP_DIR) / "upload"
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = out_dir / f"{uuid.uuid4().hex}.jpg"
        elif output_path.parent and not output_path.parent.exists():
            output_path.parent.mkdir(parents=True, exist_ok=True)

        processing = process_image_with_report(str(input_p), str(output_path), **params)

        logger.info(f"[img-adjust] 本地处理完成：{input_p} -> {output_path}")

        return {
            "output_path": str(output_path),
            "size_bytes": output_path.stat().st_size,
            "processing": processing,
        }

    def process_batch(
        self, image_urls: List[str], params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """批量处理多张远端图片，逐张处理并汇总结果。

        Args:
            image_urls: 远端图片 URL 列表
            params: 处理参数

        Returns:
            {
                "total": int,
                "success": int,
                "failed": int,
                "results": [{"image_url":..., "success":..., "public_url":..., "message":...}],
            }
        """
        results: List[Dict[str, Any]] = []
        success = 0
        failed = 0

        for url in image_urls:
            try:
                res = self.process_single(url, params)
                success += 1
                results.append({
                    "image_url": url,
                    "success": True,
                    "public_url": res["public_url"],
                    "object_name": res["object_name"],
                    "message": "处理成功",
                    "processing": res["processing"],
                })
            except Exception as e:
                failed += 1
                logger.warning(f"[img-adjust] 处理失败 url={url} err={e}")
                results.append({
                    "image_url": url,
                    "success": False,
                    "public_url": None,
                    "message": f"处理失败：{e}",
                })

        return {
            "total": len(image_urls),
            "success": success,
            "failed": failed,
            "results": results,
        }
