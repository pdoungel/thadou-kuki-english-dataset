"""Validate the existing generated Thadou-Kuki dataset without modifying data."""

from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "raw", ROOT / "out"

REQUIRED_RAW = ["vref.txt", "tcz-tczchongthu.txt", "eng-engwebp.txt"]
REQUIRED_OUT = ["parallel.tsv", "train.jsonl", "val.jsonl", "test.jsonl", "rag_corpus.jsonl"]

def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()

def main() -> int:
    errors = []
    for name in REQUIRED_RAW:
        if not (RAW / name).exists():
            errors.append(f"missing raw file: {name}")
    for name in REQUIRED_OUT:
        if not (OUT / name).exists():
            errors.append(f"missing generated file: {name}")
    if errors:
        print("\n".join("ERROR: " + x for x in errors))
        return 1

    refs, tcz, web = map(lambda n: read_lines(RAW / n),
                         ["vref.txt", "tcz-tczchongthu.txt", "eng-engwebp.txt"])
    if not (len(refs) == len(tcz) == len(web)):
        errors.append(f"raw line-count mismatch: vref={len(refs)}, tcz={len(tcz)}, web={len(web)}")

    parallel = read_lines(OUT / "parallel.tsv")
    expected = "ref\ttcz\ten_web\ten_kjv\ttcz_gospelgo"
    if not parallel or parallel[0] != expected:
        errors.append("parallel.tsv header mismatch")

    seen = set()
    malformed = 0
    for row in parallel[1:]:
        cols = row.split("\t")
        if len(cols) != 5:
            malformed += 1
            continue
        ref = cols[0].strip()
        if ref in seen:
            errors.append(f"duplicate parallel reference: {ref}")
        seen.add(ref)
    if malformed:
        errors.append(f"parallel.tsv malformed rows: {malformed}")

    split_counts = {}
    for split in ("train", "val", "test"):
        p = OUT / f"{split}.jsonl"
        count = 0
        for i, row in enumerate(read_lines(p), 1):
            try:
                obj = json.loads(row)
                msgs = obj["messages"]
                assert isinstance(msgs, list) and len(msgs) == 3
                assert all("role" in m and "content" in m for m in msgs)
                count += 1
            except Exception:
                errors.append(f"{split}.jsonl invalid record at line {i}")
        split_counts[split] = count

    stats = {
        "raw_vref_lines": len(refs),
        "raw_tcz_lines": len(tcz),
        "raw_web_lines": len(web),
        "parallel_rows": max(0, len(parallel) - 1),
        "parallel_unique_refs": len(seen),
        "parallel_duplicate_refs": max(0, len(parallel) - 1 - len(seen)),
        "sft_examples": split_counts,
        "errors": errors,
    }
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
