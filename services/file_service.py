"""通用文件服务：MinIO 上传 / 下载 / 预签名 URL。

从 tiff_crop_server/services/file_service.py 提取并通用化，
新增服务可直接复用或继承扩展。
"""

import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

from loguru import logger
from minio import Minio
from minio.error import S3Error

from config import BaseConfig


class FileService:
    """文件上传下载服务（基于 MinIO）。"""

    def __init__(self, config=None):
        """
        Args:
            config: 配置类，默认使用 BaseConfig
        """
        self.config = config or BaseConfig

        self.minio_client = Minio(
            self.config.MINIO_ENDPOINT,
            access_key=self.config.MINIO_ACCESS_KEY,
            secret_key=self.config.MINIO_SECRET_KEY,
            secure=self.config.MINIO_SECURE,
        )
        self.bucket_name = self.config.MINIO_BUCKET
        self.url_prefix = self.config.MINIO_URL_PREFIX.rstrip("/")
        self.url_expire_sec = self.config.MINIO_URL_EXPIRE_SEC

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _generate_object_name(self, local_file_path: str) -> str:
        """生成 MinIO 对象名称。

        格式：{timestamp}/{year}/{month}/{day}/{uuid}.{ext}

        Args:
            local_file_path: 本地文件路径

        Returns:
            生成的对象名称
        """
        _, ext = os.path.splitext(local_file_path)
        ext = ext.lstrip(".")

        timestamp = str(datetime.now().timestamp()).replace(".", "").replace("-", "")[:19]
        now = datetime.now()
        unique_id = str(uuid.uuid4()).replace("-", "")

        return f"{timestamp}/{now.strftime('%Y')}/{now.strftime('%m')}/{now.strftime('%d')}/{unique_id}.{ext}"

    # ------------------------------------------------------------------
    # 对外方法
    # ------------------------------------------------------------------
    def upload_file(self, local_file_path: str, object_name: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        """上传文件到 MinIO。

        Args:
            local_file_path: 本地文件路径
            object_name: MinIO 对象名称，为 None 时自动生成

        Returns:
            (object_name, file_url) 元组，失败返回 (None, None)
        """
        try:
            if object_name is None:
                object_name = self._generate_object_name(local_file_path)

            result = self.minio_client.fput_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                file_path=local_file_path,
            )
            logger.info(f"上传成功 bucket={result.bucket_name}, object={result.object_name}")

            # 生成公网访问 URL
            public_url = f"{self.url_prefix}/{self.bucket_name}/{object_name}"
            return object_name, public_url

        except S3Error as e:
            logger.error(f"MinIO 上传异常：{e}")
            return None, None
        except Exception as e:
            logger.error(f"上传文件异常：{e}")
            return None, None

    def download_file(self, object_name: str, local_file_path: str) -> bool:
        """从 MinIO 下载文件。

        Args:
            object_name: MinIO 对象名称
            local_file_path: 本地保存路径

        Returns:
            是否成功下载
        """
        try:
            Path(local_file_path).parent.mkdir(parents=True, exist_ok=True)
            self.minio_client.fget_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                file_path=local_file_path,
            )
            return True

        except S3Error as e:
            logger.error(f"MinIO 下载异常：{e}")
            return False
        except Exception as e:
            logger.error(f"下载文件异常：{e}")
            return False

    def get_presigned_url(self, object_name: str, expires: Optional[int] = None) -> Optional[str]:
        """获取预签名 URL。

        Args:
            object_name: MinIO 对象名称
            expires: 过期时间（秒），默认使用配置值

        Returns:
            预签名 URL，失败返回 None
        """
        try:
            expire_time = expires or self.url_expire_sec
            presigned_url = self.minio_client.presigned_get_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                expires=timedelta(seconds=expire_time),
            )

            # 替换为公网地址
            return presigned_url.replace(f"http://{self.config.MINIO_ENDPOINT}", self.url_prefix)

        except S3Error as e:
            logger.error(f"获取预签名 URL 异常：{e}")
            return None
        except Exception as e:
            logger.error(f"生成 URL 异常：{e}")
            return None