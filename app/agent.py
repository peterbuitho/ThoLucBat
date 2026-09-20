"""Generate -> validate -> repair loop against an OpenAI-compatible server (vLLM)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable

from openai import OpenAI

from .prompts import chat, make_repair_request, make_request, render_prompt
from .validator import PoemReport, evaluate_poem

THINK_RE = re.compile(r"<think>.*?</think>", re.S)


@dataclass
class AgentResult:
    poem: str
    report: PoemReport
    rounds: int
    history: list[dict] = field(default_factory=list)


class PoetAgent:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        n_candidates: int = 4,
        n_repairs: int = 3,
        max_rounds: int = 4,
        target: float = 0.95,
        temperature: float = 0.9,
        repair_temperature: float = 0.6,
        family: str | None = None,
    ):
        self.client = OpenAI(
            base_url=base_url or os.environ.get("VIETPOET_BASE_URL", "http://127.0.0.1:8000/v1"),
            api_key=os.environ.get("VIETPOET_API_KEY", "EMPTY"),
        )
        self.model = model or os.environ.get("VIETPOET_MODEL", "vietpoet")
        self.family = family or os.environ.get("VIETPOET_FAMILY", "qwen")   # raw-prompt format: qwen | gemma
        self.n_candidates = n_candidates
        self.n_repairs = n_repairs
        self.max_rounds = max_rounds
        self.target = target
        self.temperature = temperature
        self.repair_temperature = repair_temperature

    def _generate(self, messages: list[dict], n: int, temperature: float) -> list[str]:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            n=n,
            temperature=temperature,
            top_p=0.95,
            max_tokens=700,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        return [THINK_RE.sub("", c.message.content or "").strip() for c in resp.choices]

    def _complete_lines(self, prompt: str, n: int, temperature: float) -> list[tuple[str, float]]:
        """Sample n continuations of `prompt`, each cut at the first newline. Returns (line, mean logprob)."""
        resp = self.client.completions.create(
            model=self.model, prompt=prompt, n=n, temperature=temperature, top_p=0.95,
            max_tokens=60, stop=["\n"], logprobs=0)
        out = []
        for c in resp.choices:
            lps = [x for x in (c.logprobs.token_logprobs if c.logprobs else []) if x is not None]
            out.append((c.text.strip(), sum(lps) / len(lps) if lps else float("-inf")))
        return out

    @staticmethod
    def _violations(prefix: list[str], candidate: str) -> int:
        """Number of rule errors the candidate line causes given the lines before it."""
        if not candidate.strip():
            return 99
        idx = len(prefix) + 1
        report = evaluate_poem(prefix + [candidate])
        if len(report.lines) != idx:
            return 99
        n = sum(1 for e in report.errors if e.line == idx)
        n += sum(1 for w in report.warnings
                 if w.startswith(f"Câu {idx} lặp lại") or w.startswith(f"Câu {idx}:") or (w.startswith("Lặp vần") and f"và {idx})" in w))
        return n

    @staticmethod
    def _repeat_penalty(prefix: list[str], candidate: str) -> float:
        """0 = fresh wording; grows with word-bigram overlap with earlier lines and with repeated openings."""
        def words(l):
            return re.findall(r"\w+", l.lower())
        cw = words(candidate)
        seen = {b for l in prefix for b in zip(words(l), words(l)[1:])}
        bigrams = list(zip(cw, cw[1:]))
        overlap = sum(b in seen for b in bigrams) / len(bigrams) if bigrams else 0.0
        opening = 1.0 if len(cw) >= 2 and any(words(l)[:2] == cw[:2] for l in prefix) else 0.0
        return overlap + opening

    def create_poem_linewise(
        self,
        topic: str,
        n_lines: int = 8,
        candidates: int = 16,
        max_extra_rounds: int = 2,
        rep_penalty: float = 1.0,
        on_step: Callable[[dict], None] | None = None,
    ) -> AgentResult:
        """Write the poem one line at a time; only lines that satisfy the rules given the previous lines are kept.

        Among rule-abiding candidates the one with the best mean token logprob, minus a repetition penalty, is chosen.
        If no candidate is clean after extra rounds, the one with the fewest violations is used.
        """
        request = make_request(topic, n_lines)
        base = render_prompt(request, self.family)
        lines: list[str] = []
        history: list[dict] = []
        for k in range(n_lines):
            prompt = base + "".join(l + "\n" for l in lines)
            pool: list[tuple[int, float, str]] = []
            rounds = 0
            while True:
                for text, lp in self._complete_lines(prompt, candidates, self.temperature):
                    pool.append((self._violations(lines, text), lp, text))
                rounds += 1
                if any(v == 0 for v, _, _ in pool) or rounds > max_extra_rounds:
                    break
            best = min(pool, key=lambda x: (x[0], -(x[1] - rep_penalty * self._repeat_penalty(lines, x[2]))))
            clean = sum(1 for v, _, _ in pool if v == 0)
            step = {"line": k + 1, "violations": best[0], "clean_candidates": clean, "sampled": len(pool)}
            history.append(step)
            if on_step:
                on_step(step)
            lines.append(best[2])
        report = self._score("\n".join(lines), n_lines)
        return AgentResult("\n".join(report.lines) or "\n".join(lines), report, 0, history)

    @staticmethod
    def _score(text: str, n_lines: int | None) -> PoemReport:
        report = evaluate_poem(text)
        if n_lines and report.lines and len(report.lines) != n_lines:
            report.warnings.append(f"Yêu cầu {n_lines} câu nhưng bài thơ có {len(report.lines)} câu.")
        return report

    def create_poem(
        self,
        topic: str,
        n_lines: int | None = 8,
        on_step: Callable[[dict], None] | None = None,
    ) -> AgentResult:
        request = make_request(topic, n_lines)
        history: list[dict] = []

        def log(step: dict) -> None:
            history.append(step)
            if on_step:
                on_step(step)

        texts = self._generate(chat(request), self.n_candidates, self.temperature)
        scored = [(self._score(t, n_lines), t) for t in texts]
        best_report, best_text = max(scored, key=lambda x: x[0].score)
        log({"round": 0, "score": best_report.score, "candidates": [r.score for r, _ in scored]})

        rounds = 0
        while rounds < self.max_rounds and not (best_report.valid and best_report.score >= self.target):
            rounds += 1
            repair = make_repair_request(request, "\n".join(best_report.lines), best_report)
            texts = self._generate(chat(repair), self.n_repairs, self.repair_temperature)
            scored = [(self._score(t, n_lines), t) for t in texts]
            cand_report, cand_text = max(scored, key=lambda x: x[0].score)
            improved = cand_report.score > best_report.score
            if improved:
                best_report, best_text = cand_report, cand_text
            log({"round": rounds, "score": best_report.score, "candidates": [r.score for r, _ in scored], "improved": improved})

        return AgentResult("\n".join(best_report.lines) or best_text, best_report, rounds, history)
