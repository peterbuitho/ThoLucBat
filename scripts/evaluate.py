"""Score a served model on data/test_prompts.jsonl.

  raw   : one sample per prompt, no correction loop (measures the model itself)
  agent : full generate/validate/repair loop
  linewise : line-by-line rejection sampling (app/agent.py create_poem_linewise)

Also reports an independent cross-check score (the paper authors' scorer from the
`vietnamese-poem-classifier` package, different rule variant) so we don't only grade with
the same validator the sampler optimises.

Example: python scripts/evaluate.py --model vietpoet --tag sft-v1 --mode raw
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics as st
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.agent import PoetAgent  # noqa: E402
from app.prompts import chat  # noqa: E402
from app.validator import evaluate_poem  # noqa: E402


def distinct2(poem: str) -> float:
    toks = poem.lower().split()
    grams = list(zip(toks, toks[1:]))
    return len(set(grams)) / len(grams) if grams else 0.0


def opening_repeat(lines: list[str]) -> float:
    """Share of lines that start with the most common opening word pair (1/n = all different)."""
    starts = [tuple(l.lower().split()[:2]) for l in lines if l.strip()]
    return max(collections.Counter(starts).values()) / len(starts) if starts else 0.0


try:
    from vietnamese_poem_classifier.poem_classifier import calculate_score as _paper_score
except Exception:  # package optional
    _paper_score = None


def paper_scores(poem: str):
    if _paper_score is None or not poem.strip():
        return None
    total, _, tone, rhyme = _paper_score(poem, "luc bat")
    return {"paper_score": round(total, 4), "paper_tone": round(tone, 4), "paper_rhyme": round(rhyme, 4)}


CANDIDATES = 16
REP_PENALTY = 1.0


def run_one(agent: PoetAgent, item: dict, mode: str) -> dict:
    n_lines = 8 if "8 câu" in item["prompt"] else None
    if mode == "raw":
        text = agent._generate(chat(item["prompt"]), 1, 0.8)[0]
        report = agent._score(text, n_lines)
        rounds = 0
    elif mode == "linewise":
        res = agent.create_poem_linewise(item["topic"], n_lines or 8, candidates=CANDIDATES, rep_penalty=REP_PENALTY)
        report, rounds = res.report, sum(h["sampled"] for h in res.history) // CANDIDATES
    else:
        res = agent.create_poem(item["topic"], n_lines)
        report, rounds = res.report, res.rounds
    return {"prompt": item["prompt"], "poem": "\n".join(report.lines), "rounds": rounds,
            "length": report.length_score, "tone": report.tone_score, "rhyme": report.rhyme_score,
            "score": report.score, "distinct2": round(distinct2(" ".join(report.lines)), 4), "opening_repeat": round(opening_repeat(report.lines), 4), "valid": report.valid, **(paper_scores("\n".join(report.lines)) or {}), "errors": [e.message for e in report.errors[:6]]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--mode", choices=["raw", "agent", "linewise"], default="raw")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only-8", action="store_true", help='only prompts that ask for "8 câu"')
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--rep-penalty", type=float, default=1.0, help="linewise: penalty weight for repeated wording")
    ap.add_argument("--candidates", type=int, default=16, help="linewise: samples per line per round")
    args = ap.parse_args()
    global CANDIDATES, REP_PENALTY
    CANDIDATES, REP_PENALTY = args.candidates, args.rep_penalty

    items = [json.loads(l) for l in open(ROOT / "data/test_prompts.jsonl", encoding="utf-8")]
    if args.only_8:
        items = [it for it in items if "8 câu" in it["prompt"]]
    if args.limit:
        items = items[: args.limit]
    agent = PoetAgent(base_url=args.base_url, model=args.model)
    with ThreadPoolExecutor(args.workers) as ex:
        rows = list(ex.map(lambda it: run_one(agent, it, args.mode), items))

    out = ROOT / "data" / "eval"
    out.mkdir(exist_ok=True)
    with open(out / f"{args.tag}.{args.mode}.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    mean = lambda k: round(st.mean(r[k] for r in rows), 4)
    paper = {k: mean(k) for k in ("paper_score", "paper_tone", "paper_rhyme") if all(k in r for r in rows)}
    summary = {"tag": args.tag, "mode": args.mode, "n": len(rows), "length": mean("length"), "tone": mean("tone"),
               "rhyme": mean("rhyme"), "distinct2": mean("distinct2"), "opening_repeat": mean("opening_repeat"), "score": mean("score"), "valid_rate": round(sum(r["valid"] for r in rows) / len(rows), 3),
               "mean_rounds": mean("rounds"), **paper}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    with open(out / "summary.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
