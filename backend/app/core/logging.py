"""日志配置：结构化、可观测；不记录用户输入原文（合规）。"""
import logging
import sys


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    # 第三方库降噪
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
