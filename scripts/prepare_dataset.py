"""Build train/validation JSONL of lục-bát chat examples from the HF corpus.

Usage: python scripts/prepare_dataset.py --limit 8000
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.prompts import chat, random_request  # noqa: E402
from app.validator import evaluate_poem  # noqa: E402

GENERIC_TITLE = re.compile(r"^(không đề|vô đề|untitled|bài thơ|bài\s*\d+|thơ|\d+)\b", re.I)
LINE_SEP = "<\n>"


def detokenize(line: str) -> str:
    line = unicodedata.normalize("NFC", line).strip()
    line = re.sub(r"\s+([,.;:!?…])", r"\1", line)
    line = re.sub(r"\s+", " ", line).strip()
    return line[:1].upper() + line[1:] if line else line


def clean_title(title: str) -> str | None:
    t = re.sub(r"\s+", " ", title or "").strip()
    if not t or GENERIC_TITLE.match(t) or len(t) > 60 or len(t.split()) < 2:
        return None
    return t


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=8000, help="max training poems")
    ap.add_argument("--min-score", type=float, default=0.90)
    ap.add_argument("--min-lines", type=int, default=4)
    ap.add_argument("--max-lines", type=int, default=16)
    ap.add_argument("--val", type=int, default=300)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=ROOT / "data")
    args = ap.parse_args()

    from huggingface_hub import hf_hub_download

    src = hf_hub_download("phamson02/vietnamese-poetry-corpus", "poems_dataset.csv", repo_type="dataset")
    csv.field_size_limit(10**9)
    rng = random.Random(args.seed)

    stats: Counter = Counter()
    seen: set[str] = set()
    kept = []
    with open(src, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            stats["total"] += 1
            if row["genre"] != "lục bát" or row["specific_genre"] != "lục bát":
                stats["not_luc_bat"] += 1
                continue
            lines = [detokenize(x) for x in row["content"].split(LINE_SEP)]
            lines = [x for x in lines if x]
            n = len(lines)
            if n % 2 or not args.min_lines <= n <= args.max_lines:
                stats["bad_line_count"] += 1
                continue
            report = evaluate_poem(lines)
            if report.length_score < 1.0:
                stats["bad_length"] += 1
                continue
            if report.warnings:
                stats["warnings(dup/invalid)"] += 1
                continue
            if report.score < args.min_score:
                stats["low_score"] += 1
                continue
            key = hashlib.md5(" ".join(lines).lower().encode()).hexdigest()
            if key in seen:
                stats["duplicate"] += 1
                continue
            seen.add(key)
            kept.append({"lines": lines, "title": clean_title(row["title"]), "score": report.score, "author": row["author"]})
            stats["kept"] += 1

    print(json.dumps(stats, ensure_ascii=False, indent=1), file=sys.stderr)

    rng.shuffle(kept)
    chosen = kept[: args.limit + args.val]
    val, train = chosen[: args.val], chosen[args.val :]

    args.out.mkdir(parents=True, exist_ok=True)
    for name, poems in (("train", train), ("validation", val)):
        with open(args.out / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for p in poems:
                n = len(p["lines"])
                title = p["title"] if rng.random() < 0.9 else None
                req = random_request(rng, n, title)
                f.write(json.dumps({"messages": chat(req, "\n".join(p["lines"]))}, ensure_ascii=False) + "\n")
        print(f"wrote {len(poems)} -> {args.out / (name + '.jsonl')}", file=sys.stderr)


if __name__ == "__main__":
    main()
