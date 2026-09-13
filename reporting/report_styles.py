# -*- coding: utf-8 -*-
"""AI股神团队 - HTML 报告样式表。

由 report_generator.py 拆分而来（1.0）。原文件中 CSS 占 450+ 行，
与生成逻辑混在一起；拆出后本模块只承载样式，便于单独调整视觉。

    REPORT_CSS  完整 <style> 块，由 HTMLReportGenerator._generate_styles() 返回
"""

REPORT_CSS = '''<style>
        :root {
            --bg: #0f172a;
            --bg2: #1e293b;
            --bg3: #334155;
            --ink: #f1f5f9;
            --muted: #94a3b8;
            --rule: #475569;
            --accent: #10b981;
            --accent2: #f59e0b;
            --danger: #ef4444;
            --warning: #f59e0b;
            --info: #3b82f6;
            --success: #10b981;
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg);
            color: var(--ink);
            line-height: 1.7;
            min-height: 100vh;
        }
        
        /* ===== Cover Page ===== */
        .cover {
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            text-align: center;
            padding: 2rem;
            background: linear-gradient(135deg, var(--bg) 0%, #1a2744 50%, var(--bg2) 100%);
            position: relative;
            overflow: hidden;
        }
        
        .cover::before {
            content: '';
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle at 30% 70%, rgba(16, 185, 129, 0.08) 0%, transparent 50%),
                        radial-gradient(circle at 70% 30%, rgba(59, 130, 246, 0.06) 0%, transparent 50%);
            animation: float 20s ease-in-out infinite;
        }
        
        @keyframes float {
            0%, 100% { transform: translate(0, 0) rotate(0deg); }
            33% { transform: translate(30px, -30px) rotate(1deg); }
            66% { transform: translate(-20px, 20px) rotate(-1deg); }
        }
        
        .cover-content { position: relative; z-index: 1; }
        
        .cover-badge {
            display: inline-block;
            padding: 0.5rem 1.5rem;
            background: linear-gradient(135deg, var(--accent), var(--info));
            border-radius: 50px;
            font-size: 0.875rem;
            font-weight: 600;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            margin-bottom: 2rem;
            box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3);
        }
        
        .cover h1 {
            font-size: clamp(2.5rem, 6vw, 4.5rem);
            font-weight: 900;
            margin-bottom: 1rem;
            background: linear-gradient(135deg, var(--ink), var(--muted));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        .cover-stock {
            font-size: clamp(3rem, 8vw, 6rem);
            font-weight: 900;
            color: var(--accent);
            text-shadow: 0 0 40px rgba(16, 185, 129, 0.3);
            margin-bottom: 1rem;
            letter-spacing: -0.02em;
        }
        
        .cover-company {
            font-size: 1.25rem;
            color: var(--muted);
            margin-bottom: 3rem;
        }
        
        .cover-meta {
            display: flex;
            gap: 2rem;
            justify-content: center;
            flex-wrap: wrap;
            color: var(--muted);
            font-size: 0.875rem;
        }
        
        .cover-meta span {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .scroll-indicator {
            position: absolute;
            bottom: 2rem;
            left: 50%;
            transform: translateX(-50%);
            animation: bounce 2s infinite;
        }
        
        @keyframes bounce {
            0%, 100% { transform: translateX(-50%) translateY(0); }
            50% { transform: translateX(-50%) translateY(10px); }
        }
        
        /* ===== Table of Contents ===== */
        .toc {
            max-width: 900px;
            margin: 0 auto;
            padding: 4rem 2rem;
        }
        
        .toc h2 {
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 2rem;
            text-align: center;
        }
        
        .toc-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1rem;
        }
        
        .toc-item {
            background: var(--bg2);
            border: 1px solid var(--rule);
            border-radius: 12px;
            padding: 1.25rem;
            display: flex;
            align-items: center;
            gap: 1rem;
            transition: all 0.3s ease;
            text-decoration: none;
            color: var(--ink);
        }
        
        .toc-item:hover {
            border-color: var(--accent);
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.2);
        }
        
        .toc-emoji {
            font-size: 1.5rem;
            width: 48px;
            height: 48px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: var(--bg3);
            border-radius: 12px;
        }
        
        .toc-text h3 {
            font-size: 1rem;
            font-weight: 600;
            margin-bottom: 0.25rem;
        }
        
        .toc-text p {
            font-size: 0.875rem;
            color: var(--muted);
        }
        
        /* ===== Sections ===== */
        .section {
            max-width: 900px;
            margin: 0 auto;
            padding: 4rem 2rem;
            border-top: 1px solid var(--rule);
        }
        
        .section-header {
            display: flex;
            align-items: center;
            gap: 1rem;
            margin-bottom: 2rem;
        }
        
        .section-emoji {
            font-size: 2.5rem;
        }
        
        .section-title-group h2 {
            font-size: 1.875rem;
            font-weight: 700;
            margin-bottom: 0.25rem;
        }
        
        .section-title-group p {
            color: var(--muted);
            font-size: 0.875rem;
        }
        
        /* ===== Cards ===== */
        .card {
            background: var(--bg2);
            border: 1px solid var(--rule);
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }
        
        .card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 1rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--rule);
        }
        
        .card-agent {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }
        
        .card-agent-emoji {
            font-size: 1.5rem;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: var(--bg3);
            border-radius: 10px;
        }
        
        .card-agent-name {
            font-weight: 600;
        }
        
        .card-agent-role {
            font-size: 0.75rem;
            color: var(--muted);
        }
        
        .card-score {
            text-align: right;
        }
        
        .score-value {
            font-size: 1.5rem;
            font-weight: 700;
        }
        
        .score-label {
            font-size: 0.75rem;
            color: var(--muted);
        }
        
        .card-content {
            color: var(--muted);
            line-height: 1.8;
        }
        
        .card-content h3, .card-content h4 {
            color: var(--ink);
            margin: 1.5rem 0 0.75rem;
        }
        
        .card-content h3 { font-size: 1.125rem; }
        .card-content h4 { font-size: 1rem; }
        
        .card-content p {
            margin-bottom: 0.75rem;
        }
        
        .card-content ul, .card-content ol {
            margin-left: 1.5rem;
            margin-bottom: 0.75rem;
        }
        
        .card-content li {
            margin-bottom: 0.25rem;
        }
        
        .card-content strong {
            color: var(--ink);
        }
        
        /* ===== Signal Badges ===== */
        .signal-badges {
            display: flex;
            gap: 0.75rem;
            flex-wrap: wrap;
            margin-top: 1rem;
            padding-top: 1rem;
            border-top: 1px solid var(--rule);
        }
        
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 0.375rem;
            padding: 0.375rem 0.875rem;
            border-radius: 50px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        
        .badge-buy {
            background: rgba(16, 185, 129, 0.15);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.3);
        }
        
        .badge-sell {
            background: rgba(239, 68, 68, 0.15);
            color: var(--danger);
            border: 1px solid rgba(239, 68, 68, 0.3);
        }
        
        .badge-hold {
            background: rgba(245, 158, 11, 0.15);
            color: var(--warning);
            border: 1px solid rgba(245, 158, 11, 0.3);
        }
        
        .badge-neutral {
            background: rgba(148, 163, 184, 0.15);
            color: var(--muted);
            border: 1px solid rgba(148, 163, 184, 0.3);
        }
        
        /* ===== Score Colors ===== */
        .score-high { color: var(--success); }
        .score-medium { color: var(--warning); }
        .score-low { color: var(--danger); }
        
        /* ===== Executive Summary ===== */
        .exec-summary {
            background: linear-gradient(135deg, var(--bg2), var(--bg3));
        }
        
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin: 2rem 0;
        }
        
        .summary-stat {
            background: var(--bg);
            border: 1px solid var(--rule);
            border-radius: 12px;
            padding: 1.25rem;
            text-align: center;
        }
        
        .summary-stat-value {
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.25rem;
        }
        
        .summary-stat-label {
            font-size: 0.875rem;
            color: var(--muted);
        }
        
        /* ===== Final Decision ===== */
        .final-decision {
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.05), rgba(59, 130, 246, 0.05));
        }
        
        .decision-box {
            background: var(--bg2);
            border: 2px solid var(--accent);
            border-radius: 20px;
            padding: 2rem;
            text-align: center;
            margin: 2rem 0;
        }
        
        .decision-verdict {
            font-size: clamp(2rem, 5vw, 3rem);
            font-weight: 900;
            margin-bottom: 1rem;
        }
        
        .decision-verdict.buy { color: var(--success); }
        .decision-verdict.sell { color: var(--danger); }
        .decision-verdict.hold { color: var(--warning); }
        
        /* ===== Progress Bar ===== */
        .progress-container {
            max-width: 900px;
            margin: 0 auto;
            padding: 2rem;
        }
        
        .progress-bar {
            height: 8px;
            background: var(--bg2);
            border-radius: 4px;
            overflow: hidden;
        }
        
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--accent), var(--info));
            border-radius: 4px;
            transition: width 0.5s ease;
        }
        
        /* ===== Footer ===== */
        footer {
            text-align: center;
            padding: 3rem 2rem;
            color: var(--muted);
            font-size: 0.875rem;
            border-top: 1px solid var(--rule);
        }
        
        /* ===== Print Styles ===== */
        @media print {
            .cover { min-height: 50vh; }
            .scroll-indicator { display: none; }
            .section { page-break-inside: avoid; }
        }
        
        /* ===== Responsive ===== */
        @media (max-width: 768px) {
            .cover-meta { flex-direction: column; gap: 0.5rem; }
            .toc-grid { grid-template-columns: 1fr; }
            .summary-grid { grid-template-columns: repeat(2, 1fr); }
            .section { padding: 2rem 1rem; }
        }
        </style>'''
