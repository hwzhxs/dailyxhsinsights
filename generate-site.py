#!/usr/bin/env python3
"""
generate-site.py — XHS Daily Insights site generator
Parses daily .md reports → HTML pages → git push to GitHub Pages

Usage:
    python3 generate-site.py [--date 2026-03-15] [--push]
    python3 generate-site.py --all --push   # rebuild all dates
"""

import re
import os
import sys
import argparse
import subprocess
from datetime import datetime, date
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────
REPORTS_DIR = Path.home() / "shared/context/xhs-knowledge/ops/daily-lessons"
SITE_DIR = Path.home() / "shared/xhs-daily-site"
DAILY_DIR = SITE_DIR / "daily"
TRACKS = ["时尚", "穿搭", "网球"]
TRACK_IDS = {"时尚": "shishang", "穿搭": "chuan", "网球": "tennis"}

# ─── HTML Templates ───────────────────────────────────────────────────────────
HTML_HEAD = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — XHS Daily Insights</title>
  <link rel="stylesheet" href="{css_path}">
</head>
<body>
  <header class="site-header">
    <div class="container">
      <div>
        <h1 class="site-title">XHS Daily Insights</h1>
        <p class="site-subtitle">每日小红书内容分析 · 时尚 / 穿搭 / 网球</p>
      </div>
      <nav class="header-nav">
        <a href="{index_path}" class="nav-link">← 全部日期</a>
      </nav>
    </div>
  </header>
  <main><div class="container">
'''

HTML_FOOT = '''  </div></main>
  <footer class="site-footer">
    <div class="container">XHS Daily Insights · 数据来源 xiaohongshu-mcp · 仅供学习研究</div>
  </footer>
  <script src="{js_path}"></script>
</body>
</html>'''


def esc(s: str) -> str:
    """Escape HTML special chars."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ─── Markdown Parser ──────────────────────────────────────────────────────────

def parse_report(md_path: Path) -> dict:
    """Parse a daily .md report into structured data."""
    text = md_path.read_text(encoding="utf-8")
    result = {"date": md_path.stem, "tracks": {}}

    current_track = None
    current_note = None
    in_lessons = False
    in_methodology = False
    in_methodology = False

    for line in text.splitlines():
        # Track header  ## 时尚 / ## 穿搭 / ## 网球
        m = re.match(r"^## (时尚|穿搭|网球)\s*$", line)
        if m:
            current_track = m.group(1)
            result["tracks"][current_track] = {"meta": {}, "notes": [], "methodology": []}
            current_note = None
            in_lessons = False
            in_methodology = False
            continue

        if current_track is None:
            continue

        track = result["tracks"][current_track]

        # Track meta lines
        if line.startswith("- 今日参考账号："):
            track["meta"]["accounts"] = line[9:].strip()
        elif line.startswith("- 今日高信号标题："):
            track["meta"]["titles"] = line[10:].strip()
        elif line.startswith("- 今日竞品策略变化："):
            track["meta"]["competitor"] = line[11:].strip()

        # Note header  ### N. Title
        m = re.match(r"^### (\d+)\. (.+)$", line)
        if m:
            if current_note:
                track["notes"].append(current_note)
            current_note = {
                "num": int(m.group(1)),
                "title": m.group(2).strip(),
                "blogger": "", "keyword": "", "cover_url": "",
                "stats": {}, "save_rate": "", "replicable": "",
                "form": "", "title_struct": "",
                "tags": [], "template": "", "lessons": []
            }
            in_lessons = False
            continue

        if current_note is None:
            # Check methodology
            if line.startswith("### 本赛道今天最值得抄的方法论"):
                in_methodology = True
            elif in_methodology and line.startswith("- "):
                track["methodology"].append(line[2:].strip())
            continue

        # Note fields
        if line.startswith("- 博主："):
            current_note["blogger"] = line[4:].strip()
        elif line.startswith("- 封面图："):
            current_note["cover_url"] = line[6:].strip()
        elif line.startswith("- 来源关键词："):
            current_note["keyword"] = line[7:].strip()
        elif line.startswith("- 互动信号："):
            stats_str = line[7:].strip()
            for pat, key in [("👍 ([\d,]+)", "likes"), ("⭐ ([\d,]+)", "saves"),
                             ("💬 ([\d,]+)", "comments"), ("↗ ([\d,]+)", "shares")]:
                m2 = re.search(pat, stats_str)
                if m2:
                    current_note["stats"][key] = m2.group(1)
        elif line.startswith("- 收藏率："):
            current_note["save_rate"] = line[5:].strip()
        elif line.startswith("- 内容形态："):
            current_note["form"] = line[6:].strip()
        elif line.startswith("- 标题结构："):
            current_note["title_struct"] = line[6:].strip()
        elif line.startswith("- 标签："):
            current_note["tags"] = [t.strip() for t in line[4:].split("/") if t.strip()]
        elif line.startswith("- 标题模板候选："):
            current_note["template"] = line[8:].strip()
        elif line.startswith("- 今天可学："):
            in_lessons = True
        elif in_lessons and re.match(r"^\s+- (.+)", line):
            lesson = re.match(r"^\s+- (.+)", line).group(1).strip()
            current_note["lessons"].append(lesson)

        # Methodology section
        if line.startswith("### 本赛道今天最值得抄的方法论"):
            if current_note:
                track["notes"].append(current_note)
                current_note = None
            in_lessons = False
            in_methodology = True

        if in_methodology and current_note is None and line.startswith("- "):
            track["methodology"].append(line[2:].strip())

    # Flush last note
    if current_note and current_track:
        result["tracks"][current_track]["notes"].append(current_note)

    return result


# ─── HTML Builders ────────────────────────────────────────────────────────────

def save_rate_class(rate_str: str) -> str:
    m = re.search(r"([\d.]+)%", rate_str)
    if m and float(m.group(1)) >= 60:
        return "high"
    return ""


def replicable_class(rep_str: str) -> str:
    if "不可复制" in rep_str:
        return "blocked"
    if "可参考" in rep_str:
        return "warn"
    return "high"


CAL_STYLES = '''
  <style>
    .cal-toggle {
      display: flex; align-items: center; gap: 8px;
      font-family: var(--font-mono); font-size: 0.72rem;
      color: rgba(247,236,217,0.7); background: rgba(247,236,217,0.08);
      border: 1px solid rgba(247,236,217,0.18); border-radius: 30px;
      padding: 8px 18px; cursor: pointer; transition: all 0.4s;
      letter-spacing: 0.04em; text-transform: uppercase;
    }
    .cal-toggle:hover { background: rgba(247,236,217,0.15); color: rgba(247,236,217,0.9); }
    .cal-panel {
      display: none; position: absolute; top: calc(100% + 12px); right: 0;
      background: #fff9f0; border: 1px solid rgba(93,82,75,0.15); border-radius: 16px;
      padding: 20px; box-shadow: 0 12px 48px rgba(42,24,22,0.18); z-index: 100; min-width: 300px;
    }
    .cal-panel.open { display: block; }
    .cal-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
    .cal-month { font-family: var(--font-serif); font-size: 1rem; font-weight: 500; color: #2A1816; }
    .cal-nav { background: none; border: none; cursor: pointer; font-size: 1rem; color: #8B7D74; padding: 4px 10px; border-radius: 8px; transition: all 0.3s; }
    .cal-nav:hover { background: #F5EEE0; color: #2A1816; }
    .cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; }
    .cal-day-name { font-family: var(--font-mono); font-size: 0.6rem; color: #8B7D74; text-align: center; padding: 4px 0; letter-spacing: 0.06em; text-transform: uppercase; }
    .cal-day { aspect-ratio: 1; display: flex; align-items: center; justify-content: center; font-family: var(--font-mono); font-size: 0.7rem; border-radius: 8px; color: #8B7D74; position: relative; }
    .cal-day.has-content { color: #2A1816; font-weight: 600; cursor: pointer; text-decoration: none; }
    .cal-day.has-content::after { content: ''; position: absolute; bottom: 2px; left: 50%; transform: translateX(-50%); width: 4px; height: 4px; background: #A67C52; border-radius: 50%; }
    .cal-day.has-content:hover { background: #A67C52; color: #fff; }
    .cal-day.has-content:hover::after { background: #fff; }
    .cal-day.today-mark { outline: 2px solid #A67C52; outline-offset: 2px; }
    .cal-day.empty { color: #D0C4BB; }
  </style>'''

CAL_SCRIPT = '''  <script>
    const AVAILABLE_DATES_CAL = {dates_js};
    const dateSet = new Set(AVAILABLE_DATES_CAL);
    const todayStr = new Date().toISOString().slice(0, 10);
    if (dateSet.has(todayStr)) {{ window.location.replace("daily/" + todayStr + ".html"); }}
    const toggle = document.getElementById("calToggle");
    const panel = document.getElementById("calPanel");
    let calDate = new Date();
    toggle && toggle.addEventListener("click", (e) => {{ e.stopPropagation(); panel.classList.toggle("open"); if (panel.classList.contains("open")) renderCal(); }});
    document.addEventListener("click", () => panel && panel.classList.remove("open"));
    panel && panel.addEventListener("click", e => e.stopPropagation());
    function renderCal() {{
      const year = calDate.getFullYear(), month = calDate.getMonth();
      const firstDay = new Date(year, month, 1).getDay();
      const daysInMonth = new Date(year, month + 1, 0).getDate();
      const months = ["一月","二月","三月","四月","五月","六月","七月","八月","九月","十月","十一月","十二月"];
      let html = '<div class="cal-header"><button class="cal-nav" onclick="prevMonth()">\\u2039</button><span class="cal-month">' + year + '年' + months[month] + '</span><button class="cal-nav" onclick="nextMonth()">\\u203a</button></div><div class="cal-grid">';
      ["日","一","二","三","四","五","六"].forEach(d => html += '<div class="cal-day-name">' + d + '</div>');
      for (let i = 0; i < firstDay; i++) html += '<div class="cal-day empty"></div>';
      for (let d = 1; d <= daysInMonth; d++) {{
        const pad = String(d).padStart(2,"0"), padM = String(month+1).padStart(2,"0");
        const ds = year + "-" + padM + "-" + pad;
        const isToday = ds === todayStr;
        html += dateSet.has(ds)
          ? '<a href="daily/' + ds + '.html" class="cal-day has-content' + (isToday ? ' today-mark' : '') + '">' + d + '</a>'
          : '<div class="cal-day' + (isToday ? ' today-mark' : '') + '">' + d + '</div>';
      }}
      panel.innerHTML = html + '</div>';
    }}
    function prevMonth() {{ calDate.setMonth(calDate.getMonth()-1); renderCal(); }}
    function nextMonth() {{ calDate.setMonth(calDate.getMonth()+1); renderCal(); }}
  </script>'''


def note_card_html(note: dict, track: str, i: int) -> str:


    stats = note["stats"]
    save_cls = save_rate_class(note.get("save_rate", ""))

    stars = " ★" if save_cls == "high" else ""
    # Parse replicable from save_rate field which often includes it
    sr = note.get("save_rate", "")
    m = re.search(r"\[(.+?)\]", sr)
    if m:
        rep_label = m.group(1)
        rep_cls2 = "blocked" if "不可复制" in rep_label else ("warn" if "可参考" in rep_label else "high")
    else:
        rep_label = ""
        rep_cls2 = "high"

    save_display = re.search(r"([\d.]+%[^｜|]*)", sr)
    save_display = save_display.group(1).strip() if save_display else sr

    lessons_html = "".join(f"<li>{esc(l)}</li>" for l in note.get("lessons", []))

    # Cover image or placeholder
    cover_url = note.get("cover_url", "")
    cover_html = f'<img class="note-cover" src="{esc(cover_url)}" alt="封面" loading="lazy">' if cover_url else ''

    # Alternating card class
    alt_class = " note-card-alt" if i % 2 == 1 else ""

    return f'''
    <div class="note-card{alt_class}">
      {cover_html}
      <div class="note-num">{esc(track)} · {note["num"]:02d}</div>
      <h2 class="note-title">{esc(note["title"])}</h2>
      <div class="note-meta">
        <span>博主：{esc(note.get("blogger",""))}</span>
        <span>关键词：{esc(note.get("keyword",""))}</span>
      </div>
      <div class="note-stats">
        <div class="stat">⭐ <span>{esc(stats.get("saves","—"))}</span></div>
        <div class="stat">👍 <span>{esc(stats.get("likes","—"))}</span></div>
      </div>
      <div class="tags-row">
        <span class="tag {save_cls}">收藏率 {esc(save_display)}{stars}</span>
        {f'<span class="tag {rep_cls2}">{esc(rep_label)}</span>' if rep_label else ""}
      </div>
      {"<div class='lessons-box'><h4>今天可学</h4><ul>" + lessons_html + "</ul></div>" if lessons_html else ""}
    </div>'''


def track_panel_html(track_name: str, track_data: dict) -> str:
    tab_id = TRACK_IDS[track_name]
    meta = track_data.get("meta", {})
    notes_html = "".join(note_card_html(n, track_name, i) for i, n in enumerate(track_data.get("notes", [])))
    meth = track_data.get("methodology", [])
    meth_items = "".join(f"<li>{esc(m)}</li>" for m in meth)

    return f'''
        <div class="tab-panel" id="tab-{tab_id}">
          <div class="track-signal">
            <strong>今日参考账号：</strong>{esc(meta.get("accounts","—"))}<br>
            <strong>今日高信号标题：</strong>{esc(meta.get("titles","—"))}<br>
            <strong>竞品策略变化：</strong>{esc(meta.get("competitor","—"))}
          </div>
          <div class="notes-grid">{notes_html}</div>
          <div class="methodology">
            <h3>{esc(track_name)}赛道今日方法论</h3>
            <ul>{meth_items}</ul>
          </div>
        </div>'''


def build_daily_page(report: dict, all_dates: list = None) -> str:
    date_str = report["date"]
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        date_cn = f"{d.year}年{d.month}月{d.day}日"
    except Exception:
        date_cn = date_str

    tab_nav = "".join(
        f'<button class="tab-btn{" active" if i==0 else ""}" data-tab="{TRACK_IDS[t]}">{esc(t)}</button>'
        for i, t in enumerate(TRACKS) if t in report["tracks"]
    )

    panels = "".join(
        track_panel_html(t, report["tracks"][t])
        for i, t in enumerate(TRACKS) if t in report["tracks"]
    )
    # Set first panel active
    panels = panels.replace('class="tab-panel"', 'class="tab-panel active"', 1)

    head = HTML_HEAD.format(
        title=date_cn,
        css_path="../assets/style.css",
        index_path="../index.html"
    )
    foot = HTML_FOOT.format(js_path="../assets/main.js")

    # Calendar sidebar
    dates_js = ", ".join(f'"{x}"' for x in sorted(all_dates or [date_str], reverse=True))
    sidebar = f'''
    <aside class="cal-sidebar">
      <div class="cal-sidebar-title">浏览历史</div>
      <div id="calSidebar"></div>
    </aside>'''
    sidebar_script = f'''  <script>
    (function() {{
      const DATES = [{dates_js}];
      const dateSet = new Set(DATES);
      const pageDate = '{date_str}';
      let calDate = new Date(pageDate + 'T00:00:00');
      function render() {{
        const year = calDate.getFullYear(), month = calDate.getMonth();
        const firstDay = new Date(year, month, 1).getDay();
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        const todayStr = new Date().toISOString().slice(0, 10);
        const months = ["一月","二月","三月","四月","五月","六月","七月","八月","九月","十月","十一月","十二月"];
        let html = '<div class="cal-header"><button class="cal-nav" onclick="prevM()">\u2039</button><span class="cal-month">' + year + '年' + months[month] + '</span><button class="cal-nav" onclick="nextM()">\u203a</button></div><div class="cal-grid">';
        ['日','一','二','三','四','五','六'].forEach(d => html += '<div class="cal-day-name">' + d + '</div>');
        for (let i = 0; i < firstDay; i++) html += '<div class="cal-day empty"></div>';
        for (let d = 1; d <= daysInMonth; d++) {{
          const pad = String(d).padStart(2,'0'), padM = String(month+1).padStart(2,'0');
          const ds = year + '-' + padM + '-' + pad;
          const isToday = ds === todayStr;
          const isPage = ds === pageDate;
          let cls = 'cal-day';
          if (isPage) cls += ' viewing';
          if (isToday && !isPage) cls += ' today-mark';
          html += dateSet.has(ds)
            ? '<a href="../daily/' + ds + '.html" class="' + cls + ' has-content">' + d + '</a>'
            : '<div class="' + cls + '">' + d + '</div>';
        }}
        document.getElementById('calSidebar').innerHTML = html + '</div>';
      }}
      window.prevM = function() {{ calDate.setMonth(calDate.getMonth()-1); render(); }};
      window.nextM = function() {{ calDate.setMonth(calDate.getMonth()+1); render(); }};
      render();
    }})();
  </script>'''

    body = f'''
    <div class="page-layout">
      {sidebar}
      <div class="page-main">
        <div class="date-nav">
          <span></span>
          <span class="current-date">{esc(date_cn)}</span>
          <span></span>
        </div>
        <div class="page-header">
          <h1>{esc(d.strftime("%m月%d日") if "d" in dir() else date_cn)}报告</h1>
          <p class="date-label">生成时间：{esc(date_str)} · 范围：时尚 / 穿搭 / 网球</p>
        </div>
        <div class="track-tabs">
          <div class="tab-nav">{tab_nav}</div>
          {panels}
        </div>
      </div>
    </div>
'''
    return head + body + foot.replace('</body>', sidebar_script + '\n</body>')
    date_str = report["date"]
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        date_cn = f"{d.year}年{d.month}月{d.day}日"
    except Exception:
        date_cn = date_str

    tab_nav = "".join(
        f'<button class="tab-btn{" active" if i==0 else ""}" data-tab="{TRACK_IDS[t]}">{esc(t)}</button>'
        for i, t in enumerate(TRACKS) if t in report["tracks"]
    )

    panels = "".join(
        track_panel_html(t, report["tracks"][t])
        for i, t in enumerate(TRACKS) if t in report["tracks"]
    )
    # Set first panel active
    panels = panels.replace('class="tab-panel"', 'class="tab-panel active"', 1)

    head = HTML_HEAD.format(
        title=date_cn,
        css_path="../assets/style.css",
        index_path="../index.html"
    )
    foot = HTML_FOOT.format(js_path="../assets/main.js")

    body = f'''
    <div class="date-nav">
      <span></span>
      <span class="current-date">{esc(date_cn)}</span>
      <span></span>
    </div>
    <div class="page-header">
      <h1>{esc(d.strftime("%m月%d日") if "d" in dir() else date_cn)}报告</h1>
      <p class="date-label">生成时间：{esc(date_str)} · 范围：时尚 / 穿搭 / 网球</p>
    </div>
    <div class="track-tabs">
      <div class="tab-nav">{tab_nav}</div>
      {panels}
    </div>
'''
    return head + body + foot


def build_index(dates: list[str]) -> str:
    """Build index.html listing all dates newest first."""
    cards = ""
    dates_js = ", ".join(f'"{d}"' for d in sorted(dates, reverse=True))
    for d in sorted(dates, reverse=True):
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            date_cn = f"{dt.year}年{dt.month}月{dt.day}日"
        except Exception:
            date_cn = d
        cards += f'''
        <a href="daily/{d}.html" class="date-card">
          <div class="date-card-left">
            <div class="date-card-date">{esc(date_cn)}</div>
            <div class="date-card-meta">时尚 · 穿搭 · 网球 · 每日分析报告</div>
            <div class="date-card-tracks">
              <span class="track-badge">时尚</span>
              <span class="track-badge">穿搭</span>
              <span class="track-badge">网球</span>
            </div>
          </div>
          <div class="date-card-arrow">→</div>
        </a>'''

    head = HTML_HEAD.format(
        title="XHS Daily Insights — 每日小红书学习报告",
        css_path="assets/style.css",
        index_path="index.html"
    ).replace(
        '</head>',
        CAL_STYLES + '\n</head>'
    ).replace(
        '<nav class="header-nav">',
        '<nav class="header-nav" style="position:relative">'
    ).replace(
        '<a href="index.html" class="nav-link">← 全部日期</a>',
        '<button class="cal-toggle" id="calToggle"><i style="font-style:normal">📅</i> 选择日期</button><div class="cal-panel" id="calPanel"></div>'
    )
    foot = HTML_FOOT.format(js_path="assets/main.js").replace(
        '</body>',
        CAL_SCRIPT.format(dates_js=f'[{dates_js}]') + '\n</body>'
    )
    body = f'''
    <div class="page-header">
      <h1>每日报告</h1>
      <p class="date-label">按日期倒序 · 自动更新</p>
    </div>
    <div class="date-grid">{cards}</div>
    <script>
    const AVAILABLE_DATES = [{dates_js}];
    </script>
'''
    return head + body + foot


# ─── Main ─────────────────────────────────────────────────────────────────────

def git_push(site_dir: Path, date_str: str):
    cmds = [
        ["git", "-C", str(site_dir), "add", "-A"],
        ["git", "-C", str(site_dir), "commit", "-m", f"feat: add/update {date_str} report"],
        ["git", "-C", str(site_dir), "push", "--set-upstream", "origin", "main"],
    ]
    for cmd in cmds:
        r = subprocess.run(cmd, capture_output=True, text=True)
        print(r.stdout.strip())
        if r.returncode != 0:
            print(f"WARN: {r.stderr.strip()}")
            if "nothing to commit" in r.stderr or "nothing to commit" in r.stdout:
                continue
            if cmd[3] == "push":
                raise RuntimeError(f"Push failed: {r.stderr.strip()}")


def main():
    parser = argparse.ArgumentParser(description="Generate XHS Daily Insights site")
    parser.add_argument("--date", default=date.today().isoformat(), help="Date to generate (YYYY-MM-DD)")
    parser.add_argument("--all", action="store_true", help="Rebuild all dates")
    parser.add_argument("--push", action="store_true", help="Git push after build")
    args = parser.parse_args()

    DAILY_DIR.mkdir(parents=True, exist_ok=True)

    if args.all:
        md_files = sorted(REPORTS_DIR.glob("????-??-??.md"))
        dates_built = []
        for md_file in md_files:
            print(f"Building {md_file.name}...")
            report = parse_report(md_file)
            html = build_daily_page(report, all_dates=[f.stem for f in md_files])
            out = DAILY_DIR / f"{md_file.stem}.html"
            out.write_text(html, encoding="utf-8")
            dates_built.append(md_file.stem)
        idx = build_index(dates_built)
        (SITE_DIR / "index.html").write_text(idx, encoding="utf-8")
        print(f"Built {len(dates_built)} pages.")
    else:
        md_path = REPORTS_DIR / f"{args.date}.md"
        if not md_path.exists():
            print(f"Report not found: {md_path}")
            sys.exit(1)
        print(f"Building {args.date}...")
        report = parse_report(md_path)
        # Rebuild index with all existing dates
        existing = [p.stem for p in DAILY_DIR.glob("????-??-??.html")]
        if args.date not in existing:
            existing.append(args.date)
        html = build_daily_page(report, all_dates=existing)
        out = DAILY_DIR / f"{args.date}.html"
        out.write_text(html, encoding="utf-8")
        idx = build_index(existing)
        (SITE_DIR / "index.html").write_text(idx, encoding="utf-8")
        print(f"Written {out}")

    if args.push:
        print("Pushing to GitHub...")
        git_push(SITE_DIR, args.date if not args.all else "all")
        print("Done! Site: https://hwzhxs.github.io/dailyxhsinsights/")
    else:
        print("Build complete. Run with --push to deploy.")


if __name__ == "__main__":
    main()
