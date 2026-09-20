"""Thumbnail backfill for catalogue products - DRY-RUN by default.

Finds products that customers would see without a stored thumbnail (or, with --verify, whose thumbnail object cannot be
read back) and reports what a run would create. Only with --apply does it write anything, and then:
  * one 400 px JPEG per product at the deterministic path yash-trade/thumbs/<product id>.jpg through the tracked media
    layer (write budget enforced, identical rewrites reused, never overwrites different bytes),
  * products.thumbnail_path set ONLY if it is still empty (compare-and-set) - existing thumbnails are never replaced,
  * a checkpoint file records every processed product, so an interrupted run resumes without repeating work.
Products whose only photo is an external URL are reported, never fetched, unless --include-external is given.

    python tools/backfill_thumbnails.py --output /tmp/thumb_backfill_dry.json                # dry run (default)
    python tools/backfill_thumbnails.py --verify --limit 200 --output ...                     # also read back thumbs
    python tools/backfill_thumbnails.py --apply --checkpoint /tmp/thumb_backfill.ckpt.json --limit 50 --output ...
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402  (configures the shared core, DB and object store exactly like the API process)
from fastapi import HTTPException  # noqa: E402
from shared import core as c  # noqa: E402
from shared.media_cache import resize  # noqa: E402

THUMB_WIDTH = 400
ESTIMATED_THUMB_BYTES = 28_000
ACTOR = "system:thumbnail_backfill"


def thumb_path(product_id):
    return f"yash-trade/thumbs/{product_id}.jpg"


def classify(doc):
    if doc.get("storage_path"):
        return "missing_thumbnail_with_master"
    images = [u for u in doc.get("images", []) if isinstance(u, str) and u]
    if not images:
        return "no_image"
    if images[0].startswith("/api/files/"):
        return "missing_thumbnail_with_uploaded_photo"
    return "external_images_only"


def load_checkpoint(path):
    if path and Path(path).exists():
        return json.loads(Path(path).read_text())
    return {"done": {}, "started_at": c.stamp()}


def save_checkpoint(path, state):
    if path:
        Path(path).write_text(json.dumps(state, indent=1))


async def readable(path):
    try:
        data, kind = await asyncio.to_thread(server.get_object, path)
        return bool(data), len(data or b""), kind
    except Exception as exc:  # provider or missing object
        return False, 0, type(exc).__name__


async def scan(verify, verify_limit):
    """Read-only. Every visible or hidden, non-deleted product is looked at; nothing is written."""
    report = {"scanned": 0, "with_thumbnail": 0, "candidates": {}, "verify": {"checked": 0, "unreadable": []}, "samples": {}}
    candidates = []
    query = {"is_deleted": {"$ne": True}}
    projection = {"_id": 0, "id": 1, "title": 1, "storage_path": 1, "thumbnail_path": 1, "images": 1, "visibility": 1, "product_code": 1}
    async for doc in server.db.products.find(query, projection).sort("created_at", 1):
        report["scanned"] += 1
        if doc.get("thumbnail_path"):
            report["with_thumbnail"] += 1
            if verify and report["verify"]["checked"] < verify_limit:
                report["verify"]["checked"] += 1
                ok, size, kind = await readable(doc["thumbnail_path"])
                if not ok:
                    report["verify"]["unreadable"].append({"id": doc["id"], "thumbnail_path": doc["thumbnail_path"], "error": kind})
                    if doc.get("storage_path"):
                        candidates.append({**doc, "category": "thumbnail_object_unreadable"})
            continue
        category = classify(doc)
        candidates.append({**doc, "category": category})
    for cand in candidates:
        report["candidates"][cand["category"]] = report["candidates"].get(cand["category"], 0) + 1
        report["samples"].setdefault(cand["category"], [])
        if len(report["samples"][cand["category"]]) < 5:
            report["samples"][cand["category"]].append({k: cand.get(k) for k in ("id", "title", "product_code", "visibility", "storage_path", "images")})
    return report, candidates


async def generate(cand):
    master, kind = await asyncio.to_thread(server.get_object, cand["storage_path"])
    data, out_kind = await asyncio.to_thread(resize, master, kind or "image/jpeg", THUMB_WIDTH)
    if out_kind != "image/jpeg":
        raise ValueError(f"master is not an image ({kind})")
    return data


async def apply(candidates, checkpoint_path, limit, include_external):
    from shared.media_lifecycle import tracked_put
    state = load_checkpoint(checkpoint_path)
    results = {"created": 0, "reused_existing_object": 0, "skipped_done": 0, "skipped_external": 0, "skipped_no_master": 0,
               "already_has_thumbnail": 0, "budget_stop": False, "errors": []}
    processed = 0
    for cand in candidates:
        if processed >= limit:
            break
        pid = cand["id"]
        if pid in state["done"]:
            results["skipped_done"] += 1
            continue
        if cand["category"] == "external_images_only" and not include_external:
            results["skipped_external"] += 1
            continue
        if not cand.get("storage_path"):
            results["skipped_no_master"] += 1
            continue
        processed += 1
        try:
            data = await generate(cand)
            path = thumb_path(pid)
            put = await tracked_put(path, data, "image/jpeg", "thumbnail", ACTOR)
            # compare-and-set: never replace a thumbnail that appeared meanwhile (unless we are repairing an unreadable one)
            match = {"id": pid, "thumbnail_path": cand["thumbnail_path"]} if cand["category"] == "thumbnail_object_unreadable" \
                else {"id": pid, "$or": [{"thumbnail_path": {"$exists": False}}, {"thumbnail_path": ""}, {"thumbnail_path": None}]}
            update = await server.db.products.update_one(match, {"$set": {"thumbnail_path": path, "thumbnail_backfilled_at": c.stamp()}})
            if update.modified_count:
                results["reused_existing_object" if put.get("reused") else "created"] += 1
            else:
                results["already_has_thumbnail"] += 1
            state["done"][pid] = {"path": path, "bytes": len(data), "reused": bool(put.get("reused")), "at": c.stamp()}
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"detail": str(exc.detail)}
            if exc.status_code == 413:
                results["budget_stop"] = True
                results["errors"].append({"id": pid, "error": detail})
                break
            results["errors"].append({"id": pid, "error": detail})
        except Exception as exc:
            results["errors"].append({"id": pid, "error": f"{type(exc).__name__}: {exc}"})
        save_checkpoint(checkpoint_path, state)
    save_checkpoint(checkpoint_path, state)
    results["checkpoint_entries"] = len(state["done"])
    return results


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write thumbnails (default is a read-only dry run)")
    parser.add_argument("--verify", action="store_true", help="also read back existing thumbnails to find unreadable objects")
    parser.add_argument("--verify-limit", type=int, default=500)
    parser.add_argument("--limit", type=int, default=100, help="maximum products written per --apply run")
    parser.add_argument("--include-external", action="store_true", help="(apply) also process products whose only photo is an external URL - NOT recommended")
    parser.add_argument("--checkpoint", default="", help="(apply) resumable checkpoint file outside the repository")
    parser.add_argument("--output", required=True, help="JSON report path")
    args = parser.parse_args()
    if args.apply and not args.checkpoint:
        parser.error("--apply requires --checkpoint <file> so an interrupted run can resume")
    started = time.monotonic()
    report, candidates = await scan(args.verify, args.verify_limit)
    total = sum(report["candidates"].values())
    with_master = sum(v for k, v in report["candidates"].items() if k in {"missing_thumbnail_with_master", "thumbnail_object_unreadable"})
    report.update(mode="apply" if args.apply else "dry_run", database=server.db.name, build=c.BUILD, at=c.stamp(),
                  would_write={"objects": with_master, "estimated_bytes": with_master * ESTIMATED_THUMB_BYTES, "path_pattern": thumb_path("<product id>"),
                               "width_px": THUMB_WIDTH, "format": "image/jpeg"},
                  not_processed={"external_images_only": report["candidates"].get("external_images_only", 0),
                                 "missing_thumbnail_with_uploaded_photo": report["candidates"].get("missing_thumbnail_with_uploaded_photo", 0),
                                 "no_image": report["candidates"].get("no_image", 0)},
                  total_candidates=total)
    if args.apply:
        report["apply"] = await apply(candidates, args.checkpoint, args.limit, args.include_external)
    report["seconds"] = round(time.monotonic() - started, 2)
    Path(args.output).write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({k: report[k] for k in ("mode", "database", "scanned", "with_thumbnail", "candidates", "would_write", "not_processed", "verify", "seconds")}, indent=1, default=str))
    if args.apply:
        print(json.dumps(report["apply"], indent=1, default=str))


if __name__ == "__main__":
    asyncio.run(main())
