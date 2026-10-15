"""文件工具函数。"""

import tempfile
import urllib3
from pathlib import Path
from typing import Optional

import requests
from loguru import logger

from config import BaseConfig
import uuid

# 禁用 SSL 警告（支持自签名证书的 MinIO 等）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def download_file(url: str, dest_dir: Optional[Path] = None, allowed_extensions: Optional[set] = None) -> Path:
    """下载文件到指定目录。

    Args:
        url: 文件 URL 地址
        dest_dir: 目标目录，默认使用配置的临时目录
        allowed_extensions: 允许的扩展名集合（如 {".tiff", ".tif"}），为空则不校验

    Returns:
        下载后的文件路径

    Raises:
        ValueError: URL 无效或下载失败
    """
    if not url:
        raise ValueError("URL 不能为空")

    if dest_dir is None:
        dest_dir = BaseConfig.TEMP_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 从 URL 提取文件名
    filename = Path(url.split("/")[-1].split("?")[0])
    if not filename.suffix:
        filename = Path(f"downloaded_{tempfile.uuid4().hex}")

    # 扩展名校验（可选）
    if allowed_extensions and filename.suffix.lower() not in allowed_extensions:
        filename = Path(f"{filename.name}.{next(iter(allowed_extensions)).lstrip('.')}")

    dest_path = dest_dir / filename

    # 下载文件（禁用 SSL 验证以支持自签名证书）
    response = requests.get(
        url,
        timeout=BaseConfig.DOWNLOAD_TIMEOUT,
        stream=True,
        verify=False,
    )
    response.raise_for_status()

    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    logger.info(f"文件下载完成：{url} -> {dest_path}（{dest_path.stat().st_size} 字节）")
    return dest_path


def cleanup_temp_file(file_path: Path) -> bool:
    """清理临时文件。

    Args:
        file_path: 文件路径

    Returns:
        是否成功删除
    """
    try:
        if file_path.exists():
            file_path.unlink()
            # 如果父目录为空，也删除
            if file_path.parent.exists() and not any(file_path.parent.iterdir()):
                file_path.parent.rmdir()
            logger.debug(f"临时文件已清理：{file_path}")
            return True
        return False
    except Exception as e:
        logger.warning(f"清理临时文件失败 {file_path}: {e}")
        return False


def generate_temp_filename(suffix: str = ".tmp") -> Path:
    """生成临时文件名。

    Args:
        suffix: 文件扩展名（含点号）

    Returns:
        临时文件路径
    """
    return BaseConfig.TEMP_DIR / f"{uuid.uuid4().hex}{suffix}"