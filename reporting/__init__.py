# -*- coding: utf-8 -*-
"""HTML 研究报告生成子包。

由 1.0 对 `report_generator.py` 的职责拆分而来：CSS 与 Markdown 转换原本
和生成逻辑混在同一个 950+ 行的文件里，拆开后各自可单独调整与测试。

模块一览：

* :mod:`reporting.report_styles`   —— `REPORT_CSS`，完整 `<style>` 块。
* :mod:`reporting.report_markdown` —— `markdown_to_html()`，纯函数，
  不依赖任何实例状态（支持代码块、三级标题、粗斜体、有序/无序列表、段落）。
* :mod:`reporting.report_generator` —— `HTMLReportGenerator`：各章节生成、
  拼装与保存。这是对外唯一需要使用的入口。

红线：**报告不改写结论**。本报告层只做展示，不做任何判定；所有结论在
进入报告之前就已由各自的分析与门禁环节确定。报告中出现的内容必须与
上游给出的 `verdict` / `alpha_status` 一致，不得为了可读性软化措辞
（例如把 `INCONCLUSIVE` 渲染成看似确定的表述）。
"""
