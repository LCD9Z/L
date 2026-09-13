# -*- coding: utf-8 -*-
"""pytest 根级配置。

测试文件已迁入 `tests/`，而库模块仍在项目根目录。pytest 在 prepend 导入模式下
只会把**测试文件所在目录**插入 `sys.path`，因此需要一个根级 conftest 把项目
根目录也加进去，使 `from data_fetcher import ...` 这类既有导入继续可用。

注意：本文件必须是纯 LF 且无 BOM —— 项目有 `test_line_endings_are_lf` 守卫，
而 `run_ci.py` 的语法检查会把 BOM 报成 U+FEFF 非法字符。
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 可执行脚本已迁入 `scripts/`。少数用例需要直接审视脚本本身
# （例如 test_alpha_release_gate 检查 run_tdx_rolling_eval 是否真的调用了门禁），
# 因此把 scripts/ 也加入导入路径。
SCRIPTS = os.path.join(ROOT, "scripts")
if os.path.isdir(SCRIPTS) and SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
