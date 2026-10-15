"""示例业务服务。

展示如何基于框架开发业务服务：
- 复用 FileService 上传下载能力
- 复用 download_file / generate_temp_filename 工具
- 结构：参数校验 -> 业务处理 -> 结果返回
"""

from pathlib import Path
from typing import Dict, Any, Tuple

from loguru import logger

from config import BaseConfig
from services.file_service import FileService
from utils.file_utils import download_file, cleanup_temp_file, generate_temp_filename


class ExampleService:
    """示例业务服务（模板）。"""

    def __init__(self):
        self.file_service = FileService()

    def echo_processor(self, text: str) -> Dict[str, Any]:
        """示例：文本处理入口（占位，实际替换为业务逻辑）。

        Args:
            text: 输入文本

        Returns:
            处理结果字典
        """
        return {
            "processed": text.upper(),
            "length": len(text),
        }

    def process_remote_file(self, file_url: str) -> Tuple[str, str]:
        """示例：下载远端文件 -> 处理 -> 上传 MinIO -> 返回 URL。

        Args:
            file_url: 远端文件 URL

        Returns:
            (object_name, file_url)
        """
        input_path = None
        output_path = None
        try:
            # 1. 下载
            input_path = download_file(file_url, BaseConfig.TEMP_DIR)
            logger.info(f"已下载：{input_path}")

            # 2. 业务处理（占位，替换为真实处理逻辑）
            output_path = generate_temp_filename(suffix=".processed")
            output_path.write_bytes(input_path.read_bytes())

            # 3. 上传 MinIO
            object_name, public_url = self.file_service.upload_file(str(output_path))
            if not object_name:
                raise RuntimeError("MinIO 上传失败")

            return object_name, public_url

        finally:
            # 4. 清理临时文件
            cleanup_temp_file(input_path)
            cleanup_temp_file(output_path)