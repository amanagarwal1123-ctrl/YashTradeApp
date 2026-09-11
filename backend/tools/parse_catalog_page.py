"""Resource-limited PDF subprocess. Parent persists checkpoints; this process never publishes."""
import json
import resource
import sys
from pathlib import Path

resource.setrlimit(resource.RLIMIT_AS, (512*1024*1024, 512*1024*1024))
resource.setrlimit(resource.RLIMIT_CPU, (22, 23))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.pdf_parser import analyze_page, open_document, render_crop

if __name__ == "__main__":
    path, page, mode, maximum = sys.argv[1:5]
    try:
        if int(page) < 0:
            with open_document(path, int(maximum)) as document:
                print(json.dumps({"pages": len(document)}))
        elif len(sys.argv) > 5:
            with open_document(path, int(maximum)) as document:
                p = document[int(page)]; p.set_rotation(0)
                import fitz
                box = fitz.Rect(json.loads(sys.argv[5]))
                if p.get_textbox(box).strip():
                    raise ValueError("BAD_PHOTO_REGION: crop contains labels or field text")
                if not any((fitz.Rect(im['bbox']) & box).get_area() > box.get_area()*0.5 for im in p.get_image_info()):
                    raise ValueError("BAD_PHOTO_REGION: crop must contain a product photograph")
                image = render_crop(p, box)
            target = Path(path).parent / f"crop-{page}.png"; target.write_bytes(image)
            print(json.dumps({"crop_image": str(target)}))
        else:
            rows = analyze_page(path, int(page), mode, int(maximum))
            for i, row in enumerate(rows):
                target = Path(path).parent / f"page-{page}-row-{i}.png"
                target.write_bytes(row.pop("image")); row["image_file"] = str(target)
            print(json.dumps({"rows": rows}))
    except Exception as exc:
        print(json.dumps({"error": str(exc)[:500]}))