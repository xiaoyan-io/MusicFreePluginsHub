#!/usr/bin/env python3
"""
生成静态首页 dist/index.html，展示插件状态与 auto-next 支持
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT_DIR / "dist"
DIST_DIR.mkdir(parents=True, exist_ok=True)
PLUGINS_PATH = DIST_DIR / "plugins.json"
REPORT_PATH = DIST_DIR / "build-report.json"
INDEX_PATH = DIST_DIR / "index.html"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> None:
    plugins_data = _load_json(PLUGINS_PATH)
    report = _load_json(REPORT_PATH)

    report_plugins = {
        item.get("url"): item
        for item in report.get("plugins", {}).get("items", [])
        if isinstance(item.get("url"), str)
    }

    plugins = plugins_data.get("plugins", [])
    summary_cards = []
    entries = []
    auto_support_count = 0

    for plugin in plugins:
        url = plugin.get("url", "")
        status = report_plugins.get(url, {})
        ok = bool(status.get("ok"))
        support = bool(status.get("auto_next_support"))
        score = float(status.get("auto_next_score", 0.0) or 0.0)
        if support:
            auto_support_count += 1
        entries.append(
            {
                "name": plugin.get("name", "Unnamed"),
                "version": plugin.get("version", "-"),
                "url": url,
                "origin": status.get("origin", "singles"),
                "ok": ok,
                "support": support,
                "score": score,
            }
        )

    total = len(entries)
    summary_html = f"""
    <div class="grid gap-4 sm:grid-cols-3">
      <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 shadow-lg">
        <p class="text-sm text-slate-400">插件总数</p>
        <p class="text-3xl font-semibold text-white">{total}</p>
      </div>
      <div class="rounded-2xl border border-emerald-500/40 bg-emerald-500/10 p-4 shadow-lg">
        <p class="text-sm text-emerald-200">支持 auto-next</p>
        <p class="text-3xl font-semibold text-emerald-200">{auto_support_count}</p>
      </div>
      <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 shadow-lg">
        <p class="text-sm text-slate-400">生成时间</p>
        <p class="text-2xl font-semibold text-white">{report.get("generated_at", "-")}</p>
      </div>
    </div>
    """

    rows_html = []
    for entry in entries:
        status_badge = "✅" if entry["ok"] else "⚠️"
        auto_badge = "✅" if entry["support"] else "⚠️"
        rows_html.append(
            f"""
        <article class="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow-lg">
          <div class="flex items-center justify-between gap-2">
            <div>
              <h3 class="text-lg font-semibold text-white">{entry["name"]}</h3>
              <p class="text-sm text-slate-400">版本 {entry["version"]} · 来源 {entry["origin"]}</p>
            </div>
            <span class="text-sm text-slate-200">{status_badge}</span>
          </div>
          <p class="mt-3 text-sm text-slate-300">URL：<a href="{entry["url"]}" class="text-emerald-300 underline">{entry["url"]}</a></p>
          <div class="mt-4 flex flex-wrap gap-2 text-xs">
            <span class="rounded-full bg-slate-800/80 px-3 py-1">{auto_badge} supports auto-next (score {entry["score"]:.2f})</span>
          </div>
        </article>
        """
        )

    html_content = f"""<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>MusicFree Plugins Hub</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/tailwindcss/3.4.2/tailwind.min.css" integrity="sha512-WiVykYcZq9VHtF8vH6bBqjF0cP0kJQn5+sC6cF7zeQ8JzYqYkkW7gIc4r5gwTzQxX9gkR9T3w2cYv1GwQ2MPJw==" crossorigin="anonymous" referrerpolicy="no-referrer" />
</head>
<body class="min-h-screen bg-slate-950 text-slate-100">
  <main class="mx-auto max-w-5xl space-y-6 px-4 py-10">
    <header class="space-y-2">
      <p class="text-sm uppercase tracking-[0.4em] text-emerald-400">MusicFree Plugins Hub</p>
      <h1 class="text-4xl font-bold text-white">插件集合</h1>
      <p class="text-slate-400">健康状态由 <code>scripts/checker.py</code> 评估，auto-next 信息会显示在插件卡片上。</p>
    </header>
    {summary_html}
    <section class="space-y-4">
      {''.join(rows_html)}
    </section>
  </main>
</body>
</html>
"""
    INDEX_PATH.write_text(html_content, encoding="utf-8")


if __name__ == "__main__":
    main()
