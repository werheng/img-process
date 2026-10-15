"""API 路由模块。

新业务蓝图在此汇总导出，app.py 统一注册。
"""

# 示例蓝图（新建业务时替换/追加为自己的蓝图）
from .example import example_bp
from .img_adjust import img_adjust_bp

__all__ = ["example_bp", "img_adjust_bp"]