"""能碳数据中间件（Data Middleware）：外部数据源 → 标准 MQTT 的独立转换程序。

用法（两种等价）：
    cd platform/cloud-deploy/middleware && python runner.py --config config.json
    python -m middleware.runner --config <同上 config.json 路径>   # 从 cloud-deploy 目录
"""
__version__ = "0.1.0"
