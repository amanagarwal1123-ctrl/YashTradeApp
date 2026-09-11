"""Follow-up parser benchmark: parent+worker RSS sampled during subprocess parsing (isolated, non-live)."""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import fitz

import sys

sys.path.insert(0, "/app/backend")

import server  # noqa: F401 - backend-equivalent import baseline
from shared.pdf_jobs import run_parser
from tools.generate_catalog import generate


FIX = Path("/app/backend/fixtures/catalog-v1")
OUT = Path("/app/test_reports")


def _rss_bytes(pid: int) -> int:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                kb = int(line.split()[1])
                return kb * 1024
    except Exception:
        return 0
    return 0


def _child_pids(parent_pid: int) -> list[int]:
    try:
        raw = Path(f"/proc/{parent_pid}/task/{parent_pid}/children").read_text().strip()
        return [int(x) for x in raw.split() if x.strip().isdigit()]
    except Exception:
        return []


def _build_authoring(path: Path):
    photos = [
        "../backend/fixtures/catalog-v1/silver.jpg",
        "../backend/fixtures/catalog-v1/gold.jpg",
        "../backend/fixtures/catalog-v1/diamond.jpg",
    ]
    products = []
    for i in range(60):
        metal = ["silver", "gold", "diamond"][i % 3]
        products.append(
            {
                "product_code": f"FOLLOWUP-{metal[:1].upper()}-{i:03d}",
                "title": f"Follow-up Benchmark Product {i}",
                "metal_type": metal,
                "category": "chain" if metal != "diamond" else "ring",
                "description": "Synthetic benchmark fixture",
                "approx_weight": "10-12 g",
                "purity": "925" if metal == "silver" else "22K",
                "base_metal": "gold" if metal == "diamond" else "",
                "selling_touch": "92.5",
                "stock_status": "in_stock",
                "tags": ["benchmark", metal],
                "visibility": "hidden",
                "is_new_arrival": True,
                "is_trending": False,
                "is_pinned": False,
                "photo": photos[i % len(photos)],
            }
        )
    path.write_text(json.dumps({"products": products}, indent=2))


async def _monitor(samples: list[dict], stop: asyncio.Event, interval_s: float = 0.05):
    pid = os.getpid()
    while not stop.is_set():
        children = _child_pids(pid)
        child_rss = {str(cp): _rss_bytes(cp) for cp in children}
        samples.append(
            {
                "t": time.perf_counter(),
                "parent_rss_bytes": _rss_bytes(pid),
                "children_rss_bytes": child_rss,
                "children_total_rss_bytes": sum(child_rss.values()),
                "combined_rss_bytes": _rss_bytes(pid) + sum(child_rss.values()),
            }
        )
        await asyncio.sleep(interval_s)


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    authoring = OUT / f"followup_benchmark_authoring_60_{ts}.json"
    pdf_path = OUT / f"followup_benchmark_catalog_60_{ts}.pdf"
    _build_authoring(authoring)
    generate(authoring, pdf_path)

    with fitz.open(pdf_path) as doc:
        pages = len(doc)

    baseline_parent = _rss_bytes(os.getpid())
    warm_start = time.perf_counter()
    await run_parser(pdf_path, 0, "template_v1")
    warm_elapsed = time.perf_counter() - warm_start

    stop = asyncio.Event()
    samples: list[dict] = []
    monitor = asyncio.create_task(_monitor(samples, stop, interval_s=0.05))
    started = time.perf_counter()
    rows = 0
    for page in range(pages):
        result = await run_parser(pdf_path, page, "template_v1")
        rows += len(result.get("rows", []))
    elapsed = time.perf_counter() - started
    stop.set()
    await monitor

    peak = max((s["combined_rss_bytes"] for s in samples), default=baseline_parent)
    peak_parent = max((s["parent_rss_bytes"] for s in samples), default=baseline_parent)
    peak_children = max((s["children_total_rss_bytes"] for s in samples), default=0)

    report = {
        "timestamp_utc": ts,
        "scope": "isolated local cgroup benchmark (8GiB/4CPU), non-production entitlement",
        "concurrency": 1,
        "products_target": 60,
        "pages": pages,
        "rows_detected": rows,
        "pdf_bytes": pdf_path.stat().st_size,
        "warmup": {
            "baseline_parent_rss_bytes": baseline_parent,
            "first_page_elapsed_seconds": round(warm_elapsed, 4),
        },
        "run": {
            "elapsed_seconds": round(elapsed, 4),
            "throughput_pages_per_second": round(pages / elapsed, 4) if elapsed else None,
            "throughput_rows_per_second": round(rows / elapsed, 4) if elapsed else None,
        },
        "memory": {
            "poll_interval_seconds": 0.05,
            "sample_count": len(samples),
            "peak_parent_rss_bytes": peak_parent,
            "peak_workers_total_rss_bytes": peak_children,
            "combined_peak_rss_bytes": peak,
        },
        "artifacts": {
            "authoring_json": str(authoring),
            "pdf": str(pdf_path),
        },
    }

    out = OUT / f"followup_parser_benchmark_{ts}.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({"report": str(out), "pages": pages, "rows": rows}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
