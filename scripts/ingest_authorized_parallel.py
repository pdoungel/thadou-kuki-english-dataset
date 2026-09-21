#!/usr/bin/env python3
"""Validate and normalize an authorized Thadou-English parallel TSV.

Expected columns: ref, thadou, english.
This script only processes a file already obtained with documented redistribution rights.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, unicodedata
from pathlib import Path

def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "")
    return " ".join(s.replace("\u00a0", " ").replace("\u200b", "").split())

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--source-id", required=True)
    args = ap.parse_args()
    seen, rows, dupes = set(), 0, 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.input.open("r", encoding="utf-8-sig", newline="") as src, args.output.open("w", encoding="utf-8", newline="") as dst:
        reader = csv.DictReader(src, delimiter="\t")
        required = {"ref", "thadou", "english"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise SystemExit(f"Input must contain TSV columns: {sorted(required)}")
        writer = csv.DictWriter(dst, fieldnames=["source_id", "ref", "thadou", "english"], delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for r in reader:
            ref, t, e = norm(r["ref"]), norm(r["thadou"]), norm(r["english"])
            if not t or not e: continue
            key = (t, e)
            if key in seen: dupes += 1; continue
            seen.add(key)
            writer.writerow({"source_id":args.source_id,"ref":ref,"thadou":t,"english":e})
            rows += 1
    print(json.dumps({"source_id":args.source_id,"input_sha256":sha256(args.input),"output":str(args.output),"rows_written":rows,"duplicate_pairs_removed":dupes}, ensure_ascii=False, indent=2))

if __name__ == "__main__": main()
