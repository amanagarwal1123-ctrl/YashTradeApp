import io
import re
import time
from pathlib import Path

import fitz
from PIL import Image

from .commerce import validate_product
from .pdf_schema import DEFAULTS, FIELDS, MASTER_SIZE, PAGE, SLOTS_MM, THUMB_SIZE, VERSION, MM, field_box, photo_box


class CatalogError(ValueError):
    pass


def open_document(path, max_pages=200):
    try:
        document = fitz.open(path)
    except Exception as exc:
        raise CatalogError("INVALID_PDF: Cannot open the PDF; export it again") from exc
    if not document.is_pdf or document.needs_pass:
        document.close()
        raise CatalogError("ENCRYPTED_OR_INVALID: Supply an unencrypted PDF")
    if not 1 <= len(document) <= max_pages:
        document.close()
        raise CatalogError(f"PAGE_LIMIT: Use 1–{max_pages} pages")
    return document


def read_fields(page, slot):
    text = page.get_textbox(fitz.Rect(field_box(slot)))
    labels = dict(FIELDS)
    values, last, errors = {}, None, []
    for line in text.splitlines():
        label, sep, value = line.partition(":")
        if sep and label in labels:
            last = labels[label]
            if last in values:
                errors.append(f"{label}: repeated field")
            values[last] = value.strip()
        elif sep:
            # HTTPS URLs and wrapped descriptions are continuations, not new fields.
            if last in {"description", "video_url", "title", "selling_label"}:
                values[last] += " " + line.strip()
            else:
                errors.append(f"Unknown field label: {label}")
        elif last and line.strip():
            values[last] += " " + line.strip()
    for key, default in DEFAULTS.items():
        if not values.get(key):
            values[key] = default
    if isinstance(values.get("tags"), str):
        values["tags"] = [s.strip() for s in values["tags"].split(",") if s.strip()]
    for key in ("is_new_arrival", "is_trending", "is_pinned"):
        if isinstance(values[key], str):
            if values[key] not in {"true", "false"}:
                errors.append(f"{key}: use true or false")
            else:
                values[key] = values[key] == "true"
    data, invalid = validate_product(values)
    return data, errors + invalid


def render_crop(page, box, size=MASTER_SIZE):
    rect = fitz.Rect(box)
    if rect.is_empty or abs(rect.width - rect.height) > 0.1 or not page.rect.contains(rect):
        raise CatalogError("BAD_PHOTO_REGION: The photo must be a square inside the page")
    pix = page.get_pixmap(matrix=fitz.Matrix(size/rect.width, size/rect.height), clip=rect, alpha=False)
    image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    if image.size != (size, size):
        image = image.resize((size, size), Image.Resampling.LANCZOS)
    out = io.BytesIO(); image.save(out, "PNG")
    return out.getvalue()


def analyze_page(path, page_number, mode="template_v1", max_pages=200):
    started = time.monotonic()
    with open_document(path, max_pages) as document:
        page = document[page_number]
        rotation = page.rotation
        page.set_rotation(0)
        if abs(page.cropbox.width-PAGE[0]) > 1 or abs(page.cropbox.height-PAGE[1]) > 1 or page.cropbox.x0 or page.cropbox.y0:
            raise CatalogError("CROPBOX_UNSUPPORTED: Export full uncropped A4 pages")
        text = page.get_text()
        if mode == "legacy_pages":
            if not text.strip() and not page.get_images():
                return []
            # Explicit manual mode: square contains full page; required fields remain invalid until review.
            pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
            im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            im.thumbnail((MASTER_SIZE, MASTER_SIZE))
            square = Image.new("RGB", (MASTER_SIZE, MASTER_SIZE), (245, 245, 245)); square.paste(im, ((MASTER_SIZE-im.width)//2, (MASTER_SIZE-im.height)//2))
            out = io.BytesIO(); square.save(out, "PNG")
            return [{"block_id": f"legacy-page-{page_number+1}", "page": page_number+1, "slot": None,
                "fields": dict(DEFAULTS), "errors": ["Manual legacy page: supply product code, name, type and category; review/crop the photo"],
                "warnings": ["Explicit legacy whole-page mode; not automatic product extraction"], "image": out.getvalue(),
                "crop_points": None, "rotation": rotation, "template_version": None}]
        if f"YASH_CATALOG_TEMPLATE_VERSION: {VERSION}" not in text:
            raise CatalogError("UNSUPPORTED_LAYOUT: Use template v1 or explicitly choose legacy_pages; OCR is not implemented")
        roles = re.findall(r"^YASH_PAGE_ROLE: (GUIDE|PRODUCTS)$", text, re.M)
        if roles == ["GUIDE"]:
            return []
        if roles != ["PRODUCTS"]:
            raise CatalogError("PAGE_ROLE_REQUIRED: Use exactly one PRODUCTS or GUIDE header")
        begins = re.findall(r"^YASH_PRODUCT_BEGIN:([^\s]+)$", text, re.M)
        ends = re.findall(r"^YASH_PRODUCT_END:([^\s]+)$", text, re.M)
        if not begins or len(begins) > 2 or len(set(begins)) != len(begins) or sorted(begins) != sorted(ends):
            raise CatalogError("BOUNDARY_ERROR: Missing, duplicate, mismatched or split product markers; keep each block on one page")
        rows, used_slots = [], set()
        for code in begins:
            marks = page.search_for(f"YASH_PRODUCT_BEGIN:{code}")
            end_marks = page.search_for(f"YASH_PRODUCT_END:{code}")
            if len(marks) != 1 or len(end_marks) != 1:
                raise CatalogError("BOUNDARY_ERROR: Product markers must be unique")
            begin, end = marks[0], end_marks[0]
            slot = next((i for i, rect in enumerate(SLOTS_MM) if abs(begin.y1 - (rect[1]+6)*MM) < 4), None)
            if slot is None or slot in used_slots or abs(end.y1 - (SLOTS_MM[slot][1]+127)*MM) > 4:
                raise CatalogError("BOUNDARY_GEOMETRY: Markers must match the documented block coordinates")
            used_slots.add(slot)
            fields, errors = read_fields(page, slot)
            if fields.get("product_code") != code:
                errors.append("Product Code must match BEGIN/END markers")
            box = fitz.Rect(photo_box(slot)); warnings = []
            images = [im for im in page.get_image_info() if (fitz.Rect(im["bbox"]) & box).get_area() > box.get_area()*0.5]
            if not images:
                errors.append("photo: no valid photograph covers the square frame")
            if page.get_textbox(box).strip():
                errors.append("photo: text detected inside the photograph crop")
            if images and max(min(im["width"], im["height"]) for im in images) < 1024:
                warnings.append("Low-resolution photograph; upscaling does not restore detail")
            rows.append({"block_id": code, "page": page_number+1, "slot": slot, "fields": fields, "errors": errors,
                "warnings": warnings, "image": render_crop(page, box), "crop_points": list(box),
                "rotation": rotation, "template_version": VERSION})
        if time.monotonic() - started > 20:
            raise CatalogError("RENDER_TIMEOUT: Simplify this page before retrying")
        return rows


def thumbnail(data):
    im = Image.open(io.BytesIO(data)); im.thumbnail((THUMB_SIZE, THUMB_SIZE))
    out = io.BytesIO(); im.save(out, "PNG"); return out.getvalue()