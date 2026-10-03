"""validate_catalog.py — SageMatch CLI catalogue validator.

Usage:
    python backend/scripts/validate_catalog.py path/to/catalogue.csv
    python backend/scripts/validate_catalog.py path/to/catalogue.json

Prints a JSON report with the quality score, per-issue detail, and
repair/rejection counts so that the official organizer catalogue can
be inspected before submission without starting the full web server.

Exit codes:
    0  — catalogue parsed and accepted (may include warnings)
    1  — catalogue rejected (required fields missing or no valid products)
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure the project root is on sys.path so 'app' can be imported even when
# this script is run from the project root or from the backend/scripts/ directory.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.data_pipeline import ingest_bytes  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Validate and sanitize a software product catalogue.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        'file',
        help='Path to a CSV or JSON catalogue file.',
    )
    parser.add_argument(
        '--required-fields',
        default='name,category,description',
        help='Comma-separated list of canonical required fields (default: name,category,description).',
    )
    args = parser.parse_args()

    catalogue_path = Path(args.file)
    if not catalogue_path.exists():
        print(f'Error: file not found: {catalogue_path}', file=sys.stderr)
        return 1

    required = [f.strip() for f in args.required_fields.split(',') if f.strip()]

    try:
        products, report = ingest_bytes(
            catalogue_path.read_bytes(),
            catalogue_path.name,
            required,
        )
    except ValueError as exc:
        print(json.dumps({'error': str(exc)}, indent=2))
        return 1

    output = {
        'file': str(catalogue_path),
        'products': len(products),
        'report': report.model_dump(),
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))

    return 0 if products else 1


if __name__ == '__main__':
    sys.exit(main())
