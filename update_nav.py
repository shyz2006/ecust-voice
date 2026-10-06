# -*- coding: utf-8 -*-
import sys
import re

print("Starting nav update...")

# 1. Update bettafish/templates/index.html
with open('templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

nav_css = """
        /* ===== 华东理工大学心理中心 · 顶部全局平台导航栏与热点直通看板 ===== */
        .platform-navbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 20px;
            background: #0f172a;
            color: #f8fafc;
            border-bottom: 2px solid #000000;
            min-height: 56px;
            flex-shrink: 0;
            z-index: 100;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
        }

        .nav-brand {
            display: flex;
            align-items: center;
            gap: 12px;
            text-decoration: none;
            color: inherit;
        }

        .ecust-logo-badge {
            background: linear-gradient(135deg, #004b97, #0284c7);
            color: #ffffff;
            font-weight: 900;
            font-size: 13px;
            padding: 5px 9px;
            border-radius: 6px;
            letter-spacing: 1px;
            box-shadow: 0 2px 8px rgba(2, 132, 199, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .nav-titles {
            display: flex;
            flex-direction: column;
        }

        .nav-title-main {
            font-weight: 700;
            font-size: 15px;
            color: #ffffff;
            letter-spacing: 0.5px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .nav-title-sub {
            font-size: 11px;
            color: #94a3b8;
            font-weight: 400;
        }

        .nav-mode-switcher {
            display: flex;
            align-items: center;
            gap: 10px;
            background: rgba(15, 23, 42, 0.8);
            padding: 4px;
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.12);
        }

        .mode-tab {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 14px;
            border-radius: 8px;
            text-decoration: none;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
        }

        .mode-tab.pulse-mode {
            background: rgba(16, 185, 129, 0.12);
            border: 1px solid rgba(16, 185, 129, 0.35);
            color: #6ee7b7;
        }

        .mode-tab.pulse-mode:hover {
            background: rgba(16, 185, 129, 0.22);
            border-color: #34d399;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25);
        }

        .mode-tab.insights-mode.active {
            background: #1e293b;
            border: 1px solid #38bdf8;
            color: #38bdf8;
            box-shadow: 0 0 12px rgba(56, 189, 248, 0.25);
        }

        .mode-icon {
            font-size: 16px;
        }

        .mode-text {
            display: flex;
            flex-direction: column;
            text-align: left;
        }

        .mode-title {
            font-size: 13px;
            font-weight: 700;
            line-height: 1.2;
        }

        .mode-desc {
            font-size: 10px;
            opacity: 0.8;
            line-height: 1.2;
        }

        .mode-tag {
            font-size: 10px;
            font-weight: 700;
            background: #059669;
            color: #ffffff;
            padding: 1px 6px;
            border-radius: 4px;
            margin-left: 2px;
            letter-spacing: 0.3px;
        }

        .live-indicator {
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            width: 8px;
            height: 8px;
        }

        .live-dot {
            width: 8px;
            height: 8px;
            background-color: #10b981;
            border-radius: 50%;
            display: inline-block;
            box-shadow: 0 0 8px #10b981;
            animation: pulseDot 2s infinite;
        }

        @keyframes pulseDot {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { transform: scale(1.1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }

        .nav-user-actions {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .nav-action-btn {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.2);
            color: #e2e8f0;
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.2s;
        }

        .nav-action-btn:hover {
            background: rgba(255, 255, 255, 0.16);
            border-color: rgba(255, 255, 255, 0.4);
            color: #ffffff;
        }

        .nav-action-btn.logout-btn:hover {
            background: #dc2626;
            border-color: #ef4444;
        }

        .user-pill {
            display: flex;
            align-items: center;
            gap: 6px;
            background: rgba(30, 41, 59, 0.8);
            border: 1px solid #334155;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            color: #94a3b8;
        }

        .user-pill .user-name {
            color: #cbd5e1;
            font-weight: 600;
        }

        /* 华理本校社区直通卡片 */
        .campus-spotlight-bar {
            background: linear-gradient(135deg, #f8fafc, #f1f5f9);
            border: 2px solid #000000;
            border-radius: 8px;
            padding: 10px 16px;
            margin: 0 auto 14px;
            max-width: 950px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
            box-shadow: 3px 3px 0px rgba(0, 0, 0, 0.8);
        }

        .spotlight-brand {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .spotlight-tag {
            font-size: 13px;
            font-weight: 800;
            color: #0f172a;
            display: flex;
            align-items: center;
            gap: 4px;
        }

        .spotlight-meta {
            font-size: 12px;
            color: #64748b;
        }

        .spotlight-links {
            display: flex;
            gap: 8px;
            align-items: center;
            flex-wrap: wrap;
        }

        .spotlight-pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            text-decoration: none;
            transition: all 0.2s ease;
            border: 1.5px solid transparent;
        }

        .pill-huyou {
            background: #eff6ff;
            color: #1d4ed8;
            border-color: #93c5fd;
        }

        .pill-huyou:hover {
            background: #dbeafe;
            border-color: #2563eb;
            transform: translateY(-1px);
        }

        .pill-radar {
            background: #fef2f2;
            color: #b91c1c;
            border-color: #fca5a5;
        }

        .pill-radar:hover {
            background: #fee2e2;
            border-color: #dc2626;
            transform: translateY(-1px);
        }

        .pill-trends {
            background: #faf5ff;
            color: #6b21a8;
            border-color: #d8b4fe;
        }

        .pill-trends:hover {
            background: #f3e8ff;
            border-color: #7e22ce;
            transform: translateY(-1px);
        }

        .spotlight-cta {
            background: #004b97;
            color: #ffffff;
            padding: 5px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 700;
            text-decoration: none;
            display: flex;
            align-items: center;
            gap: 4px;
            border: 1.5px solid #000000;
            transition: all 0.2s ease;
        }

        .spotlight-cta:hover {
            background: #0284c7;
            transform: translateY(-1px);
            color: #ffffff;
        }

        /* 醒目的校园脉搏直通按钮 */
        .campus-pulse-btn-highlight {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 0 20px;
            border: 2px solid #000000;
            background: linear-gradient(135deg, #004b97, #0284c7);
            color: #ffffff !important;
            cursor: pointer;
            font-size: 14px;
            font-weight: bold;
            transition: all 0.25s ease;
            min-width: 145px;
            border-radius: 4px;
            text-decoration: none;
            box-shadow: 2px 2px 0px #000000;
        }

        .campus-pulse-btn-highlight:hover {
            background: linear-gradient(135deg, #0284c7, #0369a1);
            transform: translateY(-1px);
            box-shadow: 3px 3px 0px #000000;
            color: #ffffff !important;
        }

        .campus-pulse-btn-highlight .hot-badge {
            background: #f59e0b;
            color: #000000;
            font-size: 10px;
            font-weight: 800;
            padding: 1px 5px;
            border-radius: 4px;
            letter-spacing: 0.5px;
        }

        .search-title-group {
            text-align: center;
            margin-bottom: 12px;
        }

        .search-title-group .search-title {
            font-size: 22px;
            font-weight: 800;
            color: #0f172a;
            margin-bottom: 4px;
        }

        .search-title-group .search-subtitle {
            font-size: 12px;
            color: #64748b;
        }
"""

if "/* ===== 华东理工大学心理中心" not in content:
    content = content.replace("</style>", nav_css + "\n    </style>", 1)

navbar_html = """        <!-- 全局平台导航栏 -->
        <header class="platform-navbar">
            <a href="/" class="nav-brand" title="华东理工大学 · 校园舆情与思想动态育人平台">
                <div class="ecust-logo-badge">ECUST</div>
                <div class="nav-titles">
                    <div class="nav-title-main">
                        <span>华东理工大学 · 校园舆情与思想动态育人平台</span>
                    </div>
                    <div class="nav-title-sub">心理健康教育中心 · 融媒体智能感知系统</div>
                </div>
            </a>

            <div class="nav-mode-switcher">
                <a href="/pulse/" class="mode-tab pulse-mode" title="进入校园脉搏：本校社区信号、学生热点、梗文化与活动策划">
                    <span class="live-indicator"><span class="live-dot"></span></span>
                    <span class="mode-icon">🎓</span>
                    <div class="mode-text">
                        <span class="mode-title">校园脉搏 · 心理热点</span>
                        <span class="mode-desc">狐友圈 / 梗与玩法 / 活动策划</span>
                    </div>
                    <span class="mode-tag">本校核心</span>
                </a>
                <a href="/" class="mode-tab active insights-mode" title="微舆深度研报：全网深层舆情、思政立场研判、学术报告">
                    <span class="mode-icon">🌐</span>
                    <div class="mode-text">
                        <span class="mode-title">全网微舆 · 思想研报</span>
                        <span class="mode-desc">深层溯源 / 思政立场研判</span>
                    </div>
                </a>
            </div>

            <div class="nav-user-actions">
                <button class="nav-action-btn" onclick="document.getElementById('openConfigButton').click()" title="配置大模型供应商与参数">⚙️ LLM 配置</button>
                <div class="user-pill" title="当前登录身份">
                    <span class="user-avatar">👤</span>
                    <span class="user-name">管理员 (smy)</span>
                </div>
                <a href="/logout" class="nav-action-btn logout-btn" title="退出登录">退出</a>
            </div>
        </header>
"""

if '<header class="platform-navbar">' not in content:
    content = content.replace('<div class="container">', '<div class="container">\n' + navbar_html, 1)

spotlight_html = """            <div class="search-title-group">
                <div class="search-title">全网深层舆情与思政立场研判</div>
                <div class="search-subtitle">多智能体交叉辩论 · 思想动态深度溯源 · 思政引领与心理育人长篇报告</div>
            </div>

            <!-- 华理本校社区直通看板 -->
            <div class="campus-spotlight-bar">
                <div class="spotlight-brand">
                    <span class="live-indicator"><span class="live-dot"></span></span>
                    <span class="spotlight-tag">华理本校社区感知：</span>
                    <span class="spotlight-meta">已接入狐友圈（700+帖）、本校贴吧等</span>
                </div>
                <div class="spotlight-links">
                    <a href="/pulse/?tab=campus" class="spotlight-pill pill-huyou" title="点击查看华理本校圈真实帖子与情绪分析">
                        <span>🦊 华理狐友圈声音 (700+帖)</span>
                        <span>➔</span>
                    </a>
                    <a href="/pulse/?tab=radar" class="spotlight-pill pill-radar" title="点击查看突发热点雷达与心理透镜">
                        <span>⚡ 心理热点雷达</span>
                        <span>➔</span>
                    </a>
                    <a href="/pulse/?tab=trends" class="spotlight-pill pill-trends" title="点击查看学生流行语、句式与短视频卡点玩法">
                        <span>💡 流行梗与玩法</span>
                        <span>➔</span>
                    </a>
                </div>
                <a href="/pulse/" class="spotlight-cta" title="进入校园脉搏完整工作大屏">
                    <span>进入校园脉搏大屏</span>
                    <span>➔</span>
                </a>
            </div>"""

if '<div class="search-title">微舆 - 致力于打造简洁通用的舆情分析平台</div>' in content:
    content = content.replace(
        '<div class="search-title">微舆 - 致力于打造简洁通用的舆情分析平台</div>',
        spotlight_html,
        1
    )

old_btn = '<a class="config-button" id="campusPulseLink" href="/pulse/" style="text-decoration:none" title="校园脉搏：学生热点 / 梗文化雷达与心理活动策划">校园脉搏</a>'
new_btn = '<a class="campus-pulse-btn-highlight" id="campusPulseLink" href="/pulse/" style="text-decoration:none" title="校园脉搏：学生热点 / 狐友华理圈 / 梗文化雷达与心理活动策划"><span class="pulse-sparkle">🎓</span> 校园脉搏大屏 <span class="hot-badge">本校直达</span></a>'
if old_btn in content:
    content = content.replace(old_btn, new_btn, 1)

with open('templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("templates/index.html updated successfully")

# 2. Update CampusPulse/templates/pulse.html
with open('CampusPulse/templates/pulse.html', 'r', encoding='utf-8') as f:
    pulse_content = f.read()

if 'urlTab' not in pulse_content:
    pulse_content = pulse_content.replace(
        'loadStatus(); loadTopics();',
        'loadStatus(); loadTopics();\nconst urlTab = new URLSearchParams(window.location.search).get("tab");\nif (urlTab) showTab(urlTab);',
        1
    )

old_pulse_header = """<header>
  <div class="bar">
    <div class="brand">校园脉搏<small>CampusPulse · 心理中心热点感知</small></div>
    <div class="status" id="status">加载中…</div>
    <div class="spacer"></div>
    <button class="btn" id="collectBtn">立即采集</button>
    <a class="btn" href="../">返回微舆</a>
  </div>
  <nav class="tabs">"""

new_pulse_header = """<header>
  <div class="bar" style="background:#0f172a;color:#f8fafc;border-bottom:1px solid #1e293b;padding:8px 16px">
    <a href="/" style="display:flex;align-items:center;gap:10px;text-decoration:none;color:inherit">
      <div style="background:linear-gradient(135deg, #004b97, #0284c7);color:#fff;font-weight:900;font-size:12px;padding:4px 8px;border-radius:6px;letter-spacing:0.5px">ECUST</div>
      <div>
        <div style="font-weight:700;font-size:14px;color:#fff">华东理工大学 · 校园舆情与思想动态育人平台</div>
        <div style="font-size:11px;color:#94a3b8">心理健康教育中心 · 校园脉搏</div>
      </div>
    </a>
    <div style="display:flex;gap:8px;margin-left:16px;align-items:center">
      <a href="/pulse/" style="display:flex;align-items:center;gap:6px;background:rgba(16,185,129,0.18);border:1px solid #10b981;color:#6ee7b7;padding:5px 12px;border-radius:6px;font-size:12px;font-weight:700;text-decoration:none">
        <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#10b981;box-shadow:0 0 6px #10b981"></span>
        🎓 校园脉搏 · 心理热点
      </a>
      <a href="../" style="display:flex;align-items:center;gap:6px;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15);color:#cbd5e1;padding:5px 12px;border-radius:6px;font-size:12px;font-weight:600;text-decoration:none">
        🌐 全网微舆 · 思想研报
      </a>
    </div>
    <div class="spacer"></div>
    <div class="status" id="status" style="color:#94a3b8;font-size:12px">加载中…</div>
    <button class="btn primary" id="collectBtn" style="padding:5px 12px;font-size:12px">立即采集</button>
    <a class="btn" href="/logout" style="padding:5px 10px;font-size:12px;background:#334155;color:#f8fafc;border-color:#475569">退出</a>
  </div>
  <nav class="tabs">"""

if old_pulse_header in pulse_content:
    pulse_content = pulse_content.replace(old_pulse_header, new_pulse_header, 1)

with open('CampusPulse/templates/pulse.html', 'w', encoding='utf-8') as f:
    f.write(pulse_content)
print("CampusPulse/templates/pulse.html updated successfully")
