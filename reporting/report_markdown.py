# -*- coding: utf-8 -*-
"""AI股神团队 - 轻量 Markdown → HTML 转换。

由 report_generator.py 拆分而来（1.0）。原为 HTMLReportGenerator._markdown_to_html，
实际不依赖任何实例状态，故提取为纯函数，便于单独测试。

支持：代码块、三级标题、粗体/斜体、有序/无序列表、段落（跳过已 HTML 化的块）。
"""
import re


def markdown_to_html(text: str) -> str:
    """简单的Markdown转HTML"""
    if not text:
        return ""
    
    # 转义HTML
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    # 代码块
    text = re.sub(r'```(\w+)?\n(.*?)```', r'<pre><code>\2</code></pre>', text, flags=re.DOTALL)
    
    # 标题
    text = re.sub(r'^###\s+(.+)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)
    text = re.sub(r'^##\s+(.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^#\s+(.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    
    # 粗体和斜体
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    
    # 列表
    lines = text.split('\n')
    result = []
    in_list = False
    list_type = None
    
    for line in lines:
        stripped = line.strip()
        
        # 无序列表
        if re.match(r'^[-*+]\s+', stripped):
            if not in_list or list_type != 'ul':
                if in_list:
                    result.append(f'</{list_type}>')
                result.append('<ul>')
                in_list = True
                list_type = 'ul'
            content = re.sub(r'^[-*+]\s+', '', stripped)
            result.append(f'<li>{content}</li>')
        
        # 有序列表
        elif re.match(r'^\d+\.\s+', stripped):
            if not in_list or list_type != 'ol':
                if in_list:
                    result.append(f'</{list_type}>')
                result.append('<ol>')
                in_list = True
                list_type = 'ol'
            content = re.sub(r'^\d+\.\s+', '', stripped)
            result.append(f'<li>{content}</li>')
        
        else:
            if in_list:
                result.append(f'</{list_type}>')
                in_list = False
                list_type = None
            result.append(line)
    
    if in_list:
        result.append(f'</{list_type}>')
    
    text = '\n'.join(result)
    
    # 段落（跳过列表/标题等已HTML化的块，避免 <li> 被包进 <p>）
    _block_tags = ('<ul>', '<ol>', '<li>', '<h2>', '<h3>', '<h4>',
                   '<pre>', '<p>', '<strong>', '<em>')
    paragraphs = text.split('\n\n')
    new_paragraphs = []
    for p in paragraphs:
        p = p.strip()
        if p and not p.startswith('<') and not p.startswith('$$'):
            # 跳过列表项/已HTML化的块
            if not any(p.startswith(t) for t in _block_tags):
                p = f'<p>{p}</p>'
        new_paragraphs.append(p)
    text = '\n\n'.join(new_paragraphs)
    
    return text
