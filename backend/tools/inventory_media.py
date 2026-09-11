"""Read-only metadata inventory and bounded genuine-asset measurement. Aggregate output only.
No upload, deletion, credential output, DB write, remote listing or paid provisioning.
"""
import argparse
import asyncio
import io
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from PIL import Image


async def inventory(sample_limit):
    groups = defaultdict(set)
    async for doc in server.db.products.find({}, {"_id": 0, "storage_path": 1, "thumbnail_path": 1, "images": 1, "original_source_storage_path": 1}):
        for field, kind in [("storage_path", "masters"), ("thumbnail_path", "thumbnails"), ("original_source_storage_path", "retained_old_scans")]:
            if doc.get(field):
                groups[kind].add(doc[field])
        for url in doc.get("images", []):
            if isinstance(url, str) and "/api/files/" in url:
                groups["manual_photos"].add(url.split("/api/files/", 1)[1])
            elif url:
                groups["external_url_references"].add(url)
    async for job in server.db.import_jobs.find({}, {"_id": 0, "manifest": 1}):
        for part in job.get("manifest", {}).values():
            groups["pdf_chunks"].add(part["path"])
    async for row in server.db.import_rows.find({}, {"_id": 0, "preview_path": 1}):
        if row.get("preview_path"):
            groups["current_previews"].add(row["preview_path"])
    known_sizes = {}
    async for asset in server.db.media_assets.find({}, {"_id": 0, "path": 1, "size_bytes": 1, "purpose": 1}):
        if "size_bytes" in asset:
            known_sizes[asset["path"]] = asset["size_bytes"]
        if not any(asset["path"] in g for g in groups.values()):
            groups["superseded_previews" if asset.get("purpose") == "pdf_preview" else "unreferenced_upload_candidates"].add(asset["path"])
    measurements = []
    for kind in ("masters", "thumbnails", "manual_photos"):
        subset = sorted(groups[kind])[:sample_limit]
        values = {"kind": kind, "attempted": len(subset), "read_ok": 0, "read_failed": 0, "bytes": 0, "seconds": 0, "upstream_read_seconds": [], "jpeg92_bytes": 0, "webp92_bytes": 0}
        for path in subset:
            started = time.monotonic()
            try:
                data, _ = await asyncio.to_thread(server.get_object, path)
                values["upstream_read_seconds"].append(round(time.monotonic() - started, 6))
                known_sizes[path] = len(data)
                values["read_ok"] += 1; values["bytes"] += len(data)
                with Image.open(io.BytesIO(data)) as image:
                    for fmt, key in [("JPEG", "jpeg92_bytes"), ("WEBP", "webp92_bytes")]:
                        output = io.BytesIO(); image.convert("RGB").save(output, fmt, quality=92)
                        values[key] += len(output.getvalue())
            except Exception:
                values["read_failed"] += 1
            values["seconds"] += time.monotonic() - started
        measurements.append(values)
    return {"scope": "workspace canonical database; NOT verified production inventory", "read_only": True,
            "groups": {k: {"unique_references": len(v), "known_bytes": sum(known_sizes.get(p, 0) for p in v), "unknown_size_objects": sum(p not in known_sizes for p in v)} for k, v in groups.items()},
            "samples": measurements, "backups": "unavailable: no approved production backup inventory",
            "complete_provider_inventory": False, "compression": "Offline estimates only; no asset replaced/uploaded"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--samples-per-kind", type=int, default=3); parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not 0 <= args.samples_per_kind <= 5:
        parser.error("Choose 0-5 samples per kind")
    result = asyncio.run(inventory(args.samples_per_kind))
    Path(args.output).write_text(json.dumps(result, indent=2))