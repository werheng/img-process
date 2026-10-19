# Flask 服务基础框架

从 tiff_crop_server 中提取的通用 Flask 服务骨架，提供统一配置、统一日志、统一响应与异常处理、MinIO 文件服务等基础能力，方便后续相关服务快速搭建。

## 功能特性

- ✅ **应用工厂**：`create_app()` 一键创建应用，支持 development / production 双环境
- ✅ **统一配置**：`.env` 环境变量加载，`BaseConfig` 基类可继承扩展
- ✅ **统一日志**：loguru 控制台 + 文件双输出，自动轮转 / 保留 / 压缩
- ✅ **统一响应**：`code / request_id / success / data / message` 标准格式
- ✅ **全局异常**：统一错误码、404/405/500 兜底，业务异常 `ApiError` 快捷抛出
- ✅ **MinIO 文件服务**：上传 / 下载 / 预签名 URL
- ✅ **通用工具**：URL 下载、临时文件清理与生成
- ✅ **蓝图机制**：业务按蓝图拆分，`api/__init__.py` 统一注册
- ✅ **健康检查**：内置 `/api/health` 与根路由服务信息

## 项目结构

```
flask_service_framework/
├── app.py                    # 应用工厂 + 主入口
├── config.py                 # 配置管理（BaseConfig + 环境配置 + .env）
├── requirements.txt          # 依赖
├── config.example.env        # 配置示例
├── README.md
├── core/                     # 框架核心
│   ├── __init__.py
│   ├── logging_config.py     # loguru 日志初始化
│   └── response.py           # 统一响应 + ApiError + 全局异常处理
├── api/                      # API 蓝图（业务路由）
│   ├── __init__.py
│   └── example.py            # 示例蓝图
├── services/                 # 业务服务层
│   ├── __init__.py
│   ├── file_service.py       # MinIO 文件服务（通用）
│   └── example_service.py    # 示例服务（模板）
└── utils/
    ├── __init__.py
    └── file_utils.py         # 下载 / 清理 / 临时文件名
```

## 快速开始

### 1. 安装依赖

```bash
cd img_process
# 使用 .python-version 中指定的 Python 3.9 创建项目虚拟环境
uv venv --python 3.9 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp config.example.env .env
```

按需修改 `.env` 中的 MinIO 地址、密钥等。

### 3. 启动服务

```bash
# 开发模式（先激活虚拟环境）
source .venv/bin/activate
python app.py

# 或使用 Gunicorn（生产环境）
gunicorn -w 4 -b 0.0.0.0:15001 --pid gunicorn.pid app:app
```

服务默认运行在 `http://localhost:15001`（可通过环境变量 `PORT` 修改）。

## API 接口

### 1. 根路由

```http
GET /
```

返回服务名称、版本、端点列表。

### 2. 健康检查

```http
GET /api/example/health
```

**响应：**

```json
{
  "code": 200,
  "request_id": "a1b2c3d4",
  "success": true,
  "data": {},
  "message": "示例服务运行正常"
}
```

### 3. 示例回显（演示统一响应与耗时统计）

```http
POST /api/example/echo
Content-Type: application/json

{
  "text": "hello",
  "request_id": "a1b2c3d4"
}
```

**响应：**

```json
{
  "code": 200,
  "request_id": "a1b2c3d4",
  "success": true,
  "data": {
    "echo": "hello",
    "cost_time": 0.001
  },
  "message": "回显成功"
}
```

### 4. 示例错误接口（演示统一错误处理）

```http
GET /api/example/error
```

**响应：**

```json
{
  "code": 400,
  "request_id": "...",
  "success": false,
  "data": {},
  "message": "这是业务异常示例"
}
```

## 图片增强服务接口（img-adjust）

基于 OpenCV 实现**色彩保持**的图像增强，提供单张/批量 URL 处理与本地上传处理三类接口。
所有接口统一前缀 `/api/img-adjust`，响应遵循 `code / request_id / success / data / message` 格式。

### 通用处理参数

单张与批量处理共用同一组参数，缺省时使用下表默认值（由 `ImageAdjustService._build_params` 统一解析、类型转换与取值钳制）。

| 参数 | 类型 | 默认值 | 取值范围 | 说明 |
|------|------|--------|----------|------|
| brightness | number | 0 | -128 ~ 127 | 亮度调整 |
| contrast | number | 1.0 | 0.5 ~ 2.0 | 对比度系数 |
| reduce_overexpose | bool | false | - | 是否压暗过度曝光区域 |
| threshold | int | 220 | 1 ~ 254 | 过度曝光判定阈值（reduce_overexpose 为 true 时生效） |
| use_clahe | bool | false | - | 是否使用 CLAHE 自适应直方图均衡 |
| gamma | number | 1.0 | 0.1 ~ 3.0 | Gamma 校正（<1 变亮，>1 变暗） |
| denoise | int \| null | null | 1 ~ 100 | 非局部均值降噪强度，null 表示不降噪 |

> 处理流程（色彩保持）：仅对 LAB 色彩空间的 L 通道做亮度/对比度、过曝压缩、Gamma、CLAHE，再转回 BGR，避免色彩偏移。

### 1. 健康检查

```http
GET /api/img-adjust/health
```

**响应：**

```json
{
  "code": 200,
  "request_id": "a1b2c3d4",
  "success": true,
  "data": { "status": "ok" },
  "message": "图片处理服务运行正常"
}
```

### 2. 单张图片处理

输入为**远端图片 URL**：下载 → OpenCV 增强 → 上传 MinIO → 返回访问 URL。

```http
POST /api/img-adjust/process
Content-Type: application/json

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
```

- `image_url`：必填，远端图片地址。

**成功响应（data）：**

```json
{
  "code": 200,
  "success": true,
  "data": {
    "object_name": "1700000000000/2026/09/23/9f8e7d6c....png",
    "public_url": "http://127.0.0.1:9000/default-bucket/1700000000000/2026/09/23/9f8e7d6c....png",
    "filename": "downloaded_xxx.png"
  },
  "message": "图片处理成功"
}
```

| 字段 | 说明 |
|------|------|
| object_name | MinIO 对象名 |
| public_url | 处理结果公网访问 URL |
| filename | 输入文件在临时目录的文件名 |

**失败响应：** `image_url` 为空返回 400；下载/处理/上传失败返回 500（`success: false`）。

### 3. 批量图片处理

输入为**远端图片 URL 列表**，逐张处理并汇总。

```http
POST /api/img-adjust/process/batch
Content-Type: application/json

{
  "image_urls": [
    "https://example.com/a.png",
    "https://example.com/b.jpg"
  ],
  "brightness": 0,
  "contrast": 0.9,
  "use_clahe": true,
  "gamma": 0.9
}
```

- `image_urls`：必填，数组；单次最多 **100** 张。

**成功响应（data）：**

```json
{
  "code": 200,
  "success": true,
  "data": {
    "total": 2,
    "success": 2,
    "failed": 0,
    "results": [
      { "image_url": "https://example.com/a.png", "success": true,  "public_url": "http://.../a.png", "object_name": "...", "message": "处理成功" },
      { "image_url": "https://example.com/b.jpg", "success": true,  "public_url": "http://.../b.jpg", "object_name": "...", "message": "处理成功" }
    ]
  },
  "message": "批量处理完成：成功 2 张，失败 0 张"
}
```

- `image_urls` 为空或非数组返回 400；超过 100 张返回 400。
- 单张失败不影响其余图片，失败项在 `results` 中 `success: false` 并附 `message`。

### 4. 图片上传并处理

输入为**本地上传的图片文件**（`multipart/form-data`）：接收 → 写入临时文件 → OpenCV 增强 → 读取产物转 base64 → 删除临时文件。
**不依赖 MinIO**，处理过程中使用临时文件，处理完成后自动清理，响应仅返回 base64 编码的图像数据。

```http
POST /api/img-adjust/upload
Content-Type: multipart/form-data

file: <二进制图片文件>   （必填，字段名 file）
brightness: 0            （可选，其余参数同"通用处理参数"，缺省走默认值）
contrast: 1.2
use_clahe: true
```

**安全约束：**

- 仅允许扩展名：`.png / .jpg / .jpeg / .bmp / .gif / .webp / .tiff`
- 单文件 ≤ **10 MB**
- 临时文件名由服务端生成（`uuid` + 原始扩展名），避免路径穿越与覆盖
- 原始文件名仅作 `file_name` 元数据返回，不用于路径拼接
- 输入和输出临时文件在处理完成后（无论成功或失败）均自动删除

**成功响应（data）：**

```json
{
  "code": 200,
  "success": true,
  "data": {
    "file_name": "photo.jpg",
    "ext": ".jpg",
    "size_bytes": 123456,
    "image_base64": "/9j/4AAQSkZJRgABAQEASABIAAD..."
  },
  "message": "图片上传并处理成功"
}
```

| 字段 | 说明 |
|------|------|
| file_name | 清洗后的原始显示文件名（元数据） |
| ext | 原图扩展名 |
| size_bytes | 处理结果文件大小（字节） |
| image_base64 | 处理后图像的 base64 编码字符串，前端可用 `data:image/jpeg;base64,{image_base64}` 直接渲染 |

**失败响应：** 缺少 `file` 字段、空文件、扩展名不在白名单、超过 10MB 返回 400；图片处理失败返回 500。

### 5. 图片上传并处理（返回 URL）

输入为**本地上传的图片文件**（`multipart/form-data`）：接收 → 写入临时文件 → OpenCV 增强 → 上传 MinIO → 删除临时文件。
与 `/upload` 不同，本接口**依赖 MinIO**，处理结果上传至 MinIO 后返回文件访问 URL，不返回 base64 数据。

```http
POST /api/img-adjust/upload-url
Content-Type: multipart/form-data

file: <二进制图片文件>   （必填，字段名 file）
brightness: 0            （可选，其余参数同"通用处理参数"，缺省走默认值）
contrast: 1.2
use_clahe: true
```

**安全约束：**

- 仅允许扩展名：`.png / .jpg / .jpeg / .bmp / .gif / .webp / .tiff`
- 单文件 ≤ **10 MB**
- 临时文件名由服务端生成（`uuid` + 原始扩展名），避免路径穿越与覆盖
- 原始文件名仅作 `file_name` 元数据返回，不用于路径拼接
- 输入和输出临时文件在处理完成后（无论成功或失败）均自动删除

**成功响应（data）：**

```json
{
  "code": 200,
  "success": true,
  "data": {
    "file_name": "photo.jpg",
    "size_bytes": 123456,
    "object_name": "1700000000000/2026/09/28/abc123....jpg",
    "public_url": "http://127.0.0.1:9000/default-bucket/1700000000000/2026/09/28/abc123....jpg"
  },
  "message": "图片上传并处理成功"
}
```

| 字段 | 说明 |
|------|------|
| file_name | 清洗后的原始显示文件名（元数据） |
| size_bytes | 处理结果文件大小（字节） |
| object_name | MinIO 对象名 |
| public_url | 处理结果公网访问 URL |

**失败响应：** 缺少 `file` 字段、空文件、扩展名不在白名单、超过 10MB 返回 400；图片处理或 MinIO 上传失败返回 500。

## 上传测试页面

启动服务后，打开 `http://127.0.0.1:15001/upload`（端口以实际启动配置为准）。页面支持：

- 单文件或多文件选择，每张不超过 10 MB，单次最多 100 张。
- 调整亮度、对比度、Gamma、曝光阈值、降噪强度和处理开关。
- 七个增强参数自动保存到当前浏览器的 localStorage（键为 `img-process.enhancement-params.v1`），刷新后恢复；重置会将默认值保存到本地。
- 参数面板支持导出 `增强参数.json` 和导入 JSON。JSON 是以参数名为键的普通对象，缺少项补默认值；非法字段、类型或范围会报错并保留当前参数。文件和处理结果不持久化。
- 页面统一调用 `/api/img-adjust/upload`，直接预览原图与处理结果，并下载 JPG 图片，无需配置或连接 MinIO。
- 多文件模式逐张调用选定的上传接口，显示进度、成功与失败数量，单张失败后继续处理其他图片。
- 所有图片在结果区的缩略图列表中展示，支持上一张、下一张、点击缩略图切换；聚焦图片浏览器后也可用左右方向键切换。
- 点击原图或增强图打开大图后，可用左右按钮或方向键，按“第 1 张原图 → 第 1 张增强图 → 第 2 张原图 → 第 2 张增强图”的顺序浏览；未生成增强结果的图片只展示原图。大图中显示文件名、图片类型与位置，并同步下方当前图片。
- 处理完成后可将所有成功图片批量打包下载为 ZIP；文件名包含序号，避免同名图片覆盖；打包失败的图片会单独提示。

现有 `/api/img-adjust/process/batch` 接收图片 URL 数组，不接收本地文件；此页面的多文件上传不调用该 URL 批量接口。

页面使用 React 和 Ant Design，资源已打包在 `static/` 中，正常启动 Flask 即可使用，不依赖外部 CDN。修改 `frontend/upload.jsx` 后，在项目根目录执行以下命令重新打包：

```bash
npm ci
npm run build
```

## 开发指南

### 新建一个业务服务

1. **配置**：在 `config.py` 的 `BaseConfig` 中追加业务配置项，或在子类覆盖
2. **蓝图**：在 `api/` 下新建 `xxx.py`，定义 `xxx_bp` 与路由
3. **注册**：在 `api/__init__.py` 中导出 `xxx_bp`（框架自动注册所有导出蓝图）
4. **服务层**：在 `services/` 下实现业务类，复用 `FileService` / 工具函数
5. **统一响应**：接口内使用 `ok()` / `fail()` 或直接 `raise ApiError(...)`

### 统一响应格式

```python
from core.response import ok, fail, ApiError

# 成功
return ok(data={"key": "value"}, message="处理成功")

# 业务失败（自动转 HTTP 400 响应）
raise ApiError("参数错误", code=400, http_status=400)
```

### 复用 MinIO 文件服务

```python
from services.file_service import FileService

fs = FileService()
object_name, public_url = fs.upload_file("/path/to/file")
fs.download_file(object_name, "/local/save/path")
presigned = fs.get_presigned_url(object_name)
```

### 复用文件工具

```python
from utils.file_utils import download_file, cleanup_temp_file, generate_temp_filename

local_path = download_file("http://.../file.tiff", suffix=".tiff")
out_path = generate_temp_filename(suffix=".result")
cleanup_temp_file(local_path)
```

## 新增一个服务接口的完整流程

假设要加一个"图片压缩"服务，步骤如下：

### 第 1 步：在 `api/` 下新建蓝图文件

```python
# api/image.py
import time
from flask import Blueprint, request
from loguru import logger
from core.response import ok, fail, ApiError

image_bp = Blueprint("image", __name__, url_prefix="/api/image")

@image_bp.route("/compress", methods=["POST"])
def compress():
    """图片压缩接口。"""
    start = time.time()
    data = request.get_json(silent=True) or {}

    image_url = data.get("image_url")
    if not image_url:
        raise ApiError("image_url 参数不能为空", code=400, http_status=400)

    # 调用服务层处理...
    result = {"compressed_url": "http://...", "ratio": 0.65}

    return ok(
        data={**result, "cost_time": round(time.time() - start, 3)},
        message="压缩成功",
    )
```

### 第 2 步：在 `api/__init__.py` 中导出

```python
# api/__init__.py
from .example import example_bp
from .image import image_bp          # ← 新增这一行

__all__ = ["example_bp", "image_bp"] # ← 加上名字
```

**就这两步，框架自动完成蓝图注册，接口立即可用。**`app.py` 不需要动。

### 第 3 步（可选）：在 `services/` 下实现业务逻辑

如果业务较复杂，拆到服务层而不是塞在路由里：

```python
# services/image_service.py
from pathlib import Path
from loguru import logger
from config import BaseConfig
from services.file_service import FileService
from utils.file_utils import download_file, cleanup_temp_file, generate_temp_filename

class ImageService:
    def __init__(self):
        self.file_service = FileService()

    def compress_and_upload(self, image_url: str) -> dict:
        input_path = None
        output_path = None
        try:
            input_path = download_file(image_url, BaseConfig.TEMP_DIR)
            output_path = generate_temp_filename(suffix=".jpg")
            # ... 压缩逻辑 ...
            object_name, public_url = self.file_service.upload_file(str(output_path))
            return {"compressed_url": public_url, "ratio": 0.65}
        finally:
            cleanup_temp_file(input_path)
            cleanup_temp_file(output_path)
```

然后在路由里调用：

```python
# api/image.py（修订）
from services.image_service import ImageService

@image_bp.route("/compress", methods=["POST"])
def compress():
    data = request.get_json(silent=True) or {}
    image_url = data.get("image_url")
    if not image_url:
        raise ApiError("image_url 参数不能为空", code=400, http_status=400)

    service = ImageService()
    result = service.compress_and_upload(image_url)
    return ok(data=result, message="压缩成功")
```

### 第 4 步（可选）：在 `config.py` 追加业务配置

```python
class BaseConfig:
    ...
    # 图片压缩配置
    IMAGE_QUALITY = int(os.environ.get("IMAGE_QUALITY", "85"))
    IMAGE_MAX_WIDTH = int(os.environ.get("IMAGE_MAX_WIDTH", "4096"))
```

同时在 `config.example.env` 里补上对应变量。

---

## 总结流程图

```
新建 api/xxx.py → 定义 xxx_bp + 路由
        ↓
api/__init__.py 导出 xxx_bp        ← 框架自动注册，到此接口已可用
        ↓
（可选）services/xxx_service.py    ← 复杂业务拆到服务层
        ↓
（可选）config.py 追加配置项        ← 需要新参数时
```

最小改动就是前两步——新建蓝图文件 + 导出，接口就能跑。`app.py` 始终不用改。



## 配置说明

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| FLASK_ENV | 运行环境（development/production） | development |
| FLASK_SECRET_KEY | Flask 密钥 | flask-service-secret-key-dev |
| FLASK_DEBUG | 调试模式 | True |
| SERVICE_NAME | 服务名称（根路由展示） | Flask Base Service |
| SERVICE_VERSION | 服务版本 | 1.0.0 |
| LOG_LEVEL | 日志级别 | DEBUG |
| LOG_FILE | 日志文件路径 | logs/service.log |
| LOG_ROTATION | 日志轮转大小 | 10 MB |
| LOG_RETENTION | 日志保留天数 | 10 days |
| TEMP_DIR | 临时文件目录 | temp |
| MINIO_ENDPOINT | MinIO 端点 | 127.0.0.1:9000 |
| MINIO_ACCESS_KEY | MinIO 访问密钥 | - |
| MINIO_SECRET_KEY | MinIO 密钥 | - |
| MINIO_BUCKET | MinIO 桶 | default-bucket |
| MINIO_URL_PREFIX | MinIO 公网访问前缀 | http://127.0.0.1:9000 |
| MINIO_URL_EXPIRE_SEC | URL 有效期（秒） | 6000 |
| MINIO_SECURE | 是否使用 HTTPS | False |
| DOWNLOAD_TIMEOUT | 下载超时（秒） | 300 |
| UPLOAD_TIMEOUT | 上传超时（秒） | 300 |
| PORT | 开发服务器端口 | 15001 |

## 技术栈

- **框架**: Flask 2.3+
- **日志**: loguru
- **文件存储**: MinIO Python SDK
- **HTTP**: requests
- **环境管理**: python-dotenv

## 注意事项

1. **临时文件清理**：业务处理完毕后使用 `cleanup_temp_file` 清理，避免占用磁盘
2. **并发处理**：开发模式 `debug=True` 不建议生产使用，生产环境使用 Gunicorn
3. **MinIO 连接**：默认 `secure=False` 支持自签名证书，生产环境按需调整
4. **请求体限制**：默认最大 100MB，可通过 `MAX_CONTENT_LENGTH` 调整
