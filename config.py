"""Flask 服务基础配置管理。

支持 .env 环境变量加载，内置 development / production 两套环境配置。
新服务只需继承 BaseConfig 追加业务配置项，并在 config_map 中注册。
"""

import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent

# 尝试加载 .env 文件
try:
    from dotenv import load_dotenv

    env_path = BASE_DIR / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        print(f"已加载环境变量文件：{env_path}")
except ImportError:
    pass  # python-dotenv 未安装时忽略

# ---------------------------------------------------------------------------
# 日志配置（模块级常量，供 core/logging_config.py 使用）
# ---------------------------------------------------------------------------
LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG")
LOG_FILE = os.environ.get("LOG_FILE", str(BASE_DIR / "logs" / "service.log"))
LOG_ROTATION = os.environ.get("LOG_ROTATION", "10 MB")
LOG_RETENTION = os.environ.get("LOG_RETENTION", "10 days")


def _env_bool(key: str, default: bool = False) -> bool:
    """读取布尔型环境变量。"""
    return os.environ.get(key, str(default)).lower() in ("true", "1", "yes", "on")


def _env_int(key: str, default: int) -> int:
    """读取整型环境变量，支持表达式（如 100 * 1024 * 1024）。"""
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(eval(raw, {"__builtins__": {}}, {}))
    except Exception:
        return default


class BaseConfig:
    """基础配置类，所有环境的公共配置。"""

    # ------------------------------------------------------------------
    # Flask 基础配置
    # ------------------------------------------------------------------
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "flask-service-secret-key-dev")
    DEBUG = _env_bool("FLASK_DEBUG", True)
    JSON_AS_ASCII = False  # JSON 响应保留中文

    # ------------------------------------------------------------------
    # 服务信息（根路由展示，子类可覆盖）
    # ------------------------------------------------------------------
    SERVICE_NAME = os.environ.get("SERVICE_NAME", "Flask Base Service")
    SERVICE_VERSION = os.environ.get("SERVICE_VERSION", "1.0.0")

    # ------------------------------------------------------------------
    # 临时文件目录
    # ------------------------------------------------------------------
    TEMP_DIR = Path(os.environ.get("TEMP_DIR", str(BASE_DIR / "temp")))
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 请求/响应
    # ------------------------------------------------------------------
    MAX_CONTENT_LENGTH = _env_int("MAX_CONTENT_LENGTH", 100 * 1024 * 1024)  # 100MB
    DOWNLOAD_TIMEOUT = _env_int("DOWNLOAD_TIMEOUT", 300)  # 下载超时（秒）
    UPLOAD_TIMEOUT = _env_int("UPLOAD_TIMEOUT", 300)  # 上传超时（秒）

    # ------------------------------------------------------------------
    # MinIO 文件服务配置
    # ------------------------------------------------------------------
    MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "127.0.0.1:9000")
    MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "admin")
    MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "Admin@123456")
    MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "default-bucket")
    MINIO_URL_PREFIX = os.environ.get("MINIO_URL_PREFIX", "http://220.154.142.85:9000")
    MINIO_URL_EXPIRE_SEC = int(os.environ.get("MINIO_URL_EXPIRE_SEC", "6000"))
    MINIO_SECURE = _env_bool("MINIO_SECURE", False)


class DevelopmentConfig(BaseConfig):
    """开发环境配置。"""

    DEBUG = True


class ProductionConfig(BaseConfig):
    """生产环境配置。"""

    DEBUG = False
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY_PROD", BaseConfig.SECRET_KEY)


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config(config_name: str = None):
    """按名称获取配置类。

    Args:
        config_name: 配置名称（development/production），默认 default

    Returns:
        配置类
    """
    if config_name is None:
        config_name = "default"
    return config_map[config_name]