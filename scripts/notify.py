#!/usr/bin/env python3
"""
Telegram 通知脚本

- 汇总 build-report.json 和插件信息
- 发送消息到指定 BOT/CHAT
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT_DIR / "dist"
REPORT_PATH = DIST_DIR / "build-report.json"
PLUGINS_PATH = DIST_DIR / "plugins.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _build_message(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("🎯 MusicFree Plugins Hub 构建通知")
    lines.append(f"- strict mode: `{report.get('strict', False)}`")
    lines.append(f"- 生成时间: {report.get('generated_at', '-')}")

    sources = report.get("sources", [])
    source_ok = sum(1 for s in sources if s.get("ok"))
    lines.append(f"- 源健康: {source_ok}/{len(sources)}")

    plugins = report.get("plugins", {})
    auto_items = plugins.get("items", [])
    auto_support = sum(1 for p in auto_items if p.get("auto_next_support"))
    lines.append(f"- 插件 (ok/failed): {plugins.get('ok', 0)}/{plugins.get('failed', 0)} (auto-next 支持: {auto_support}/{len(auto_items)})")

    failed_sources = [s.get("url") for s in sources if not s.get("ok")]
    if failed_sources:
        lines.append("- 失败源:")
        for url in failed_sources[:3]:
            lines.append(f"  - {url}")

    failed_plugins = [p for p in auto_items if not p.get("ok")]
    if failed_plugins:
        lines.append("- 失败插件:")
        for plugin in failed_plugins[:3]:
            lines.append(f"  - {plugin.get('name', '-')}")

    deploy_url = os.getenv("PAGES_URL")
    if deploy_url:
        lines.append(f"- 部署链接: {deploy_url}")

    return "\n".join(lines)


def send_telegram(token: str, chat_id: str, text: str) -> None:
    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    resp = httpx.post(endpoint, data=payload, timeout=10.0)
    resp.raise_for_status()


def main() -> None:
    report = _load_json(REPORT_PATH)
    if not report:
        print("跳过 Telegram 通知：未找到 build-report.json")
        return

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("未配置 Telegram 参数，跳过通知")
        return

    message = _build_message(report)
    try:
        send_telegram(token, chat_id, message)
        print("Telegram 消息发送完成")
    except httpx.HTTPError as exc:
        print(f"Telegram 发送失败: {exc}")


if __name__ == "__main__":
    main()
