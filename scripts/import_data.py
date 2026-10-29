"""Run:  python -m scripts.import_data [path/to/file.csv]"""
import json
import sys

from app.services.ingestion import import_csv

if __name__ == "__main__":
    summary = import_csv(sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps(summary, indent=2))
