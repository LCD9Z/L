# -*- coding: utf-8 -*-
"""统一日志工具：支持级别、文件输出和彩色终端。

用法：
    from log_utils import get_logger
    log = get_logger(__name__)
    log.info("行情获取成功")
    log.warning("腾讯兜底触发")
    log.error("接口全部不可用")

配置（环境变量）：
    LOG_LEVEL: DEBUG / INFO / WARNING / ERROR (默认 INFO)
    LOG_FILE:  日志文件路径（可选，不设则仅输出到终端）
"""
import logging
import os
import sys
from typing import List

_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
_FILE = os.environ.get("LOG_FILE", "")
_FORMAT = "[%(asctime)s] %(levelname)-5s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _setup():
    global _configured
    if _configured:
        return
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if _FILE:
        handlers.append(logging.FileHandler(_FILE, encoding="utf-8"))
    logging.basicConfig(level=getattr(logging, _LEVEL, logging.INFO),
                        format=_FORMAT, datefmt=_DATEFMT, handlers=handlers,
                        force=True)
    _configured = True


def get_logger(name=None):
    """获取 logger，自动初始化全局配置。"""
    _setup()
    return logging.getLogger(name or "stock_god")


# 便捷函数，供不愿引入 logger 对象的模块直接调用
def info(msg, name=None):
    get_logger(name).info(msg)

def warning(msg, name=None):
    get_logger(name).warning(msg)

def error(msg, name=None):
    get_logger(name).error(msg)
