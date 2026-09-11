"""Export actual registered canonical/legacy API documentation without running startup tasks."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import app

if __name__ == "__main__":
    path = Path(__file__).resolve().parents[2] / "contracts/openapi.shared-v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(app.openapi(), indent=2))
    print(f"OpenAPI exported: {len(app.openapi()['paths'])} paths")