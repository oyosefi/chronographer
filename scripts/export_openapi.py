import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "app"))

from app.main import app  # noqa: E402


def rendered_schema() -> str:
    # JSON is valid YAML and avoids a runtime-only YAML dependency.
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    destination = ROOT / "openapi.yaml"
    rendered = rendered_schema()
    if args.check:
        if (
            not destination.exists()
            or destination.read_text(encoding="utf-8") != rendered
        ):
            print("openapi.yaml is out of date; run python scripts/export_openapi.py")
            return 1
        return 0
    destination.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
