#!/usr/bin/env python3
"""
插件健康检查器

- 校验源可访问性与 JSON 结构
- 下载并校验插件 JS（状态码、体积、Content-Type）
- 生成 dist/build-report.json 与 dist/build-report.md
- 可选严格模式：剔除不稳定源/插件
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

import httpx
from loguru import logger

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_JSON_PATH = ROOT_DIR / "src" / "data" / "origins.json"
DIST_DIR = ROOT_DIR / "dist"
DIST_DIR.mkdir(parents=True, exist_ok=True)
REPORT_JSON_PATH = DIST_DIR / "build-report.json"
REPORT_MD_PATH = DIST_DIR / "build-report.md"

OK_STATUS = {200, 206, 301, 302, 303, 307, 308}
MAX_CONCURRENCY = 10
REQUEST_TIMEOUT = 12.0
RETRIES = 2
MIN_JS_BYTES = 64
AUTO_NEXT_KEYWORDS = [
    "autoNext",
    "auto-next",
    "auto_next",
    "supports auto-next",
    "supports autoNext",
    "onAutoNext",
    "auto next",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _error_to_dict(exc: Exception) -> dict:
    error: dict = {"type": type(exc).__name__, "message": str(exc)}
    if isinstance(exc, httpx.HTTPStatusError):
        error["status_code"] = exc.response.status_code
        error["url"] = str(exc.request.url)
    elif isinstance(exc, httpx.RequestError):
        error["url"] = str(exc.request.url)
    return error


def _load_origins() -> dict:
    try:
        return json.loads(DATA_JSON_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("读取源配置失败: {}", exc)
        return {"sources": [], "singles": []}


def _detect_auto_next(content: bytes) -> dict:
    if not content:
        return {"support": False, "score": 0.0}
    lowered = content.decode("utf-8", errors="ignore").lower()
    unique_matches = {kw.lower() for kw in AUTO_NEXT_KEYWORDS if kw.lower() in lowered}
    score = len(unique_matches) / len(AUTO_NEXT_KEYWORDS)
    return {"support": bool(unique_matches), "score": round(score, 2)}


async def _probe(
    url: str,
    client: httpx.AsyncClient,
    expect_json: bool = False,
) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        start = asyncio.get_event_loop().time()
        try:
            resp = await client.get(url)
            elapsed_ms = int((asyncio.get_event_loop().time() - start) * 1000)
            payload = None
            if expect_json:
                payload = resp.json()
            return {
                "ok": resp.status_code in OK_STATUS,
                "status_code": resp.status_code,
                "latency_ms": elapsed_ms,
                "headers": dict(resp.headers),
                "content": resp.content,
                "payload": payload,
            }
        except Exception as exc:
            last_error = exc
            logger.warning(
                "请求失败[{}/{}]: {} ({})", attempt, RETRIES, url, str(exc)
            )
            await asyncio.sleep(0.5 * attempt)
    return {
        "ok": False,
        "status_code": getattr(getattr(last_error, "response", None), "status_code", None),
        "latency_ms": None,
        "headers": {},
        "error": _error_to_dict(last_error) if last_error else {},
    }


async def _check_source(
    url: str,
    client: httpx.AsyncClient,
) -> tuple[dict, list[dict]]:
    result = {"url": url, "ok": False}
    probe = await _probe(url, client, expect_json=True)
    result.update(
        {
            "status_code": probe.get("status_code"),
            "latency_ms": probe.get("latency_ms"),
            "ok": probe.get("ok", False),
        }
    )

    if not probe.get("ok"):
        result["error"] = probe.get("error") or {"message": "请求失败"}
        return result, []

    payload = probe.get("payload") or {}
    plugins = payload.get("plugins") if isinstance(payload, dict) else None
    if not isinstance(plugins, list):
        result["ok"] = False
        result["error"] = {"message": "JSON 结构异常，未找到 plugins 列表"}
        return result, []

    result["plugin_count"] = len(plugins)
    return result, plugins


async def _check_plugin(
    plugin: Dict[str, Any],
    origin: str,
    client: httpx.AsyncClient,
    strict: bool,
) -> dict:
    url = plugin.get("url")
    name = plugin.get("name") or plugin.get("id") or url or "unknown"
    if not url:
        return {
            "name": name,
            "url": url,
            "ok": False,
            "origin": origin,
            "error": {"message": "缺少 url 字段"},
        }

    probe = await _probe(url, client, expect_json=False)
    content: bytes = probe.get("content") or b""
    size = len(content)
    content_type = (probe.get("headers") or {}).get("content-type", "")
    hash_sha1 = hashlib.sha1(content).hexdigest() if content else None
    auto_detection = _detect_auto_next(content)

    status_ok = probe.get("ok", False)
    size_ok = size >= MIN_JS_BYTES
    type_ok = True
    if strict:
        type_ok = "javascript" in content_type or "text/plain" in content_type

    ok = status_ok and size_ok and type_ok

    result = {
        "name": name,
        "url": url,
        "origin": origin,
        "ok": ok,
        "status_code": probe.get("status_code"),
        "latency_ms": probe.get("latency_ms"),
        "size_bytes": size,
        "hash_sha1": hash_sha1,
        "content_type": content_type,
        "auto_next_score": auto_detection["score"],
        "auto_next_support": auto_detection["support"],
    }

    if not ok:
        result["error"] = probe.get("error") or {}
        if not status_ok:
            result["error"].setdefault("message", "状态码异常或不可达")
        elif not size_ok:
            result["error"].setdefault("message", f"文件过小(<{MIN_JS_BYTES} bytes)")
        elif strict and not type_ok:
            result["error"].setdefault("message", "Content-Type 非 JavaScript，严格模式拒绝")

    return result


async def _check_plugins(
    plugins: Iterable[dict],
    origin: str,
    client: httpx.AsyncClient,
    strict: bool,
) -> List[dict]:
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async def _wrap(plugin: dict) -> dict:
        async with sem:
            return await _check_plugin(plugin, origin, client, strict)

    tasks = [_wrap(p) for p in plugins]
    return await asyncio.gather(*tasks)


def _write_report(report: dict) -> None:
    REPORT_JSON_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    sources = report.get("sources", [])
    plugins = report.get("plugins", {})
    failed_sources = [s for s in sources if not s.get("ok")]
    failed_plugins = [p for p in plugins.get("items", []) if not p.get("ok")]
    ok_plugins = [p for p in plugins.get("items", []) if p.get("ok")]

    lines: list[str] = []
    lines.append(f"# Build Report ({report.get('generated_at', '-')})")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- strict mode: `{report.get('strict')}`")
    lines.append(
        f"- sources: `{len(sources)}` total / `{len(failed_sources)}` failed / `{len(sources) - len(failed_sources)}` ok"
    )
    lines.append(
        f"- plugins: `{plugins.get('total', 0)}` total / `{len(ok_plugins)}` ok / `{len(failed_plugins)}` failed"
    )
    lines.append(f"- output: `{REPORT_JSON_PATH.name}`")

    auto_items = plugins.get("items", [])
    auto_total = len(auto_items)
    auto_ok = sum(1 for p in auto_items if p.get("auto_next_support"))
    if auto_total:
        lines.append(
            f"- 自动播放回调支持 (auto-next): `{auto_ok}` / `{auto_total}`"
        )

    if failed_sources:
        lines.append("")
        lines.append("## Failed Sources")
        for s in failed_sources:
            status = s.get("status_code")
            suffix = f" (status {status})" if status else ""
            err = s.get("error", {})
            lines.append(
                f"- `{s.get('url', '-')}`{suffix}: {err.get('type', '-')}: {err.get('message', '-')}"
            )

    if failed_plugins:
        lines.append("")
        lines.append("## Failed Plugins")
        for p in failed_plugins:
            status = p.get("status_code")
            suffix = f" (status {status})" if status else ""
            err = p.get("error", {})
            lines.append(
                f"- `{p.get('name', '-')}` `{p.get('url', '-')}`{suffix}: {err.get('type', '-')}: {err.get('message', '-')}"
            )

    if auto_items:
        lines.append("")
        lines.append("## Auto-next Support Details")
        for p in auto_items:
            badge = "✅" if p.get("auto_next_support") else "⚠️"
            lines.append(
                f"- {badge} `{p.get('name', '-')}` {p.get('url', '-')} score `{p.get('auto_next_score', 0):.2f}`"
            )

    REPORT_MD_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


async def run(strict: bool) -> int:
    origins = _load_origins()
    if not origins:
        logger.error("源配置为空，无法检查")
        return 1

    report: dict = {
        "generated_at": _utc_now_iso(),
        "strict": strict,
        "sources": [],
        "plugins": {"total": 0, "items": []},
    }

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "MusicFreePluginsHub/health-checker"},
    ) as client:
        # 检查 sources
        for source_url in origins.get("sources", []):
            logger.info("检查源: {}", source_url)
            src_result, plugins = await _check_source(source_url, client)
            report["sources"].append(src_result)
            if src_result.get("ok"):
                plugin_results = await _check_plugins(plugins, source_url, client, strict)
                report["plugins"]["items"].extend(plugin_results)

        # 检查 singles
        singles = origins.get("singles", [])
        if singles:
            logger.info("检查单独插件: {} 个", len(singles))
            single_results = await _check_plugins(singles, "singles", client, strict)
            report["plugins"]["items"].extend(single_results)

    report["plugins"]["total"] = len(report["plugins"]["items"])
    ok_items = [p for p in report["plugins"]["items"] if p.get("ok")]
    failed_items = [p for p in report["plugins"]["items"] if not p.get("ok")]

    report["plugins"]["ok"] = len(ok_items)
    report["plugins"]["failed"] = len(failed_items)
    report["filtered_plugins"] = [
        {"name": p.get("name"), "url": p.get("url")}
        for p in ok_items
    ]

    _write_report(report)
    logger.success(
        "健康检查完成: sources {} ok / {} failed | plugins {} ok / {} failed",
        len(report["sources"]) - len([s for s in report["sources"] if not s.get("ok")]),
        len([s for s in report["sources"] if not s.get("ok")]),
        len(ok_items),
        len(failed_items),
    )
    if strict and failed_items:
        logger.warning("严格模式下存在失败插件，建议剔除后再构建")
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="MusicFree 插件健康检查器")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式：只接受状态码正常且 JS 体积满足条件的插件",
    )
    args = parser.parse_args()

    strict_env = os.getenv("STRICT_CHECK", "0") == "1"
    strict = args.strict or strict_env

    exit_code = asyncio.run(run(strict))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
