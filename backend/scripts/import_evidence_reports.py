import argparse
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.evidence_import_service import import_evidence_files


def main():
    """Run the script entry point."""
    parser = argparse.ArgumentParser(
        description="Incrementally import new TSP/HSP/sketch PDFs into evidence_db.csv."
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="PDF file paths or folders containing PDFs.",
    )
    parser.add_argument(
        "--source-type",
        choices=["tsp", "hsp", "sonic", "sketch"],
        default=None,
        help="Force one parser for all input PDFs. If omitted, the script infers it from folder/name.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report changes without writing evidence_db.csv.",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Replace existing evidence_id rows with newly parsed rows.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="When a path is a folder, scan PDFs recursively.",
    )
    args = parser.parse_args()

    result = import_evidence_files(
        paths=args.paths,
        source_type=args.source_type,
        dry_run=args.dry_run,
        replace_existing=args.replace_existing,
        recursive=args.recursive,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()