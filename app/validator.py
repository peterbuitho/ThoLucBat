"""Rule-based lục-bát validator with line/syllable-level errors.

Score = 0.1*length + 0.3*tone + 0.6*rhyme (weights from the Vietnamese poem
generation paper, arXiv:2401.01078).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field

TONE_MARKS = {
    "̀": "huyen",
    "́": "sac",
    "̃": "nga",
    "̉": "hoi",
    "̣": "nang",
}
TONE_NAMES = {
    "ngang": "ngang (không dấu)",
    "huyen": "huyền",
    "sac": "sắc",
    "nga": "ngã",
    "hoi": "hỏi",
    "nang": "nặng",
}
BANG = {"ngang", "huyen"}

SYLLABLE_RE = re.compile(
    r"^(ngh|gh|gi|qu|ng|nh|ph|th|tr|ch|kh|[bcdđghklmnpqrstvx])?"
    r"([aăâeêioôơuưy]+)(ch|ng|nh|[cmnpt])?$"
)
WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

NEAR_RHYMES = [
    {"au", "âu"}, {"ay", "ây"}, {"ôi", "ơi"},
    {"ong", "ông"}, {"ăng", "âng"}, {"anh", "ênh", "inh"},
    {"en", "ên", "iên"}, {"ăn", "ân"},
    {"am", "ăm", "âm"}, {"em", "êm"}, {"om", "ôm"},
]

LENGTHS = {"luc": 6, "bat": 8}
W_LENGTH, W_TONE, W_RHYME = 0.1, 0.3, 0.6
NEAR_RHYME_CREDIT = 0.95


@dataclass
class Syllable:
    text: str
    base: str
    tone: str
    rime: str | None
    valid: bool

    @property
    def is_bang(self) -> bool:
        return self.tone in BANG


def parse_syllable(word: str) -> Syllable:
    nfd = unicodedata.normalize("NFD", word.lower())
    tone = "ngang"
    kept = []
    for ch in nfd:
        if ch in TONE_MARKS:
            tone = TONE_MARKS[ch]
        else:
            kept.append(ch)
    base = unicodedata.normalize("NFC", "".join(kept))
    m = SYLLABLE_RE.match(base)
    if not m:
        return Syllable(word, base, tone, None, False)
    return Syllable(word, base, tone, _normalize_rime(m.group(2), m.group(3) or ""), True)


def _normalize_rime(vowels: str, final: str) -> str:
    if vowels.startswith("uyê"):
        vowels = "iê" + vowels[3:]
    elif vowels.startswith("yê"):
        vowels = "iê" + vowels[2:]
    elif vowels == "uy":
        vowels = "i"
    elif len(vowels) > 1 and vowels[0] == "o" and vowels[1] in "aăeê":
        vowels = vowels[1:]
    elif len(vowels) > 1 and vowels[0] == "u" and vowels[1] in "êâơ":
        vowels = vowels[1:]
    if vowels == "y":
        vowels = "i"
    return vowels + final


def rhyme_credit(a: Syllable, b: Syllable) -> float:
    if not (a.valid and b.valid):
        return 0.0
    if a.rime == b.rime:
        return 1.0
    if any(a.rime in g and b.rime in g for g in NEAR_RHYMES):
        return NEAR_RHYME_CREDIT
    return 0.0


@dataclass
class PoemError:
    line: int
    kind: str
    message: str
    pos: int | None = None
    word: str | None = None


@dataclass
class PoemReport:
    lines: list[str]
    length_score: float
    tone_score: float
    rhyme_score: float
    score: float
    errors: list[PoemError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.length_score == 1.0 and self.score >= 0.95 and not self.warnings

    def to_dict(self) -> dict:
        d = asdict(self)
        d["valid"] = self.valid
        return d

    def error_summary(self, max_items: int = 12) -> str:
        items = [e.message for e in self.errors[:max_items]] + self.warnings + self.notes
        return "\n".join(f"- {m}" for m in items)


def clean_poem(text: str) -> list[str]:
    """Extract poem lines from raw model output (drops fences, blanks, markdown)."""
    text = unicodedata.normalize("NFC", text)
    lines = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("```"):
            continue
        s = re.sub(r"^\s*(?:[-*•>]+|\d+[.)])\s*", "", s)
        s = s.strip("*_# ").strip()
        if WORD_RE.search(s):
            lines.append(s)
    return lines


def _words(line: str) -> list[str]:
    return WORD_RE.findall(unicodedata.normalize("NFC", line))


def evaluate_poem(poem: str | list[str]) -> PoemReport:
    lines = clean_poem(poem) if isinstance(poem, str) else list(poem)
    n = len(lines)
    errors: list[PoemError] = []
    warnings: list[str] = []
    notes: list[str] = []

    if n == 0:
        return PoemReport([], 0.0, 0.0, 0.0, 0.0, [PoemError(0, "empty", "Bài thơ trống.")])
    if n % 2:
        warnings.append(f"Bài thơ có {n} câu (số lẻ); lục bát cần các cặp câu 6-8, thiếu câu bát cuối.")

    parsed = [[parse_syllable(w) for w in _words(line)] for line in lines]
    kinds = ["luc" if i % 2 == 0 else "bat" for i in range(n)]

    length_ok = 0
    line_ok = [False] * n
    for i, syls in enumerate(parsed):
        need = LENGTHS[kinds[i]]
        if len(syls) == need:
            length_ok += 1
            line_ok[i] = True
        else:
            name = "lục" if kinds[i] == "luc" else "bát"
            errors.append(PoemError(i + 1, "length", f"Câu {i + 1} (câu {name}) có {len(syls)} tiếng, cần đúng {need} tiếng.", None, None))
        for j, s in enumerate(syls):
            if not s.valid:
                warnings.append(f"Câu {i + 1}: '{s.text}' không phải tiếng Việt hợp lệ.")

    tone_passed = tone_total = 0

    def check(i: int, pos: int, want_bang: bool):
        nonlocal tone_passed, tone_total
        tone_total += 1
        if not line_ok[i]:
            return
        s = parsed[i][pos - 1]
        if s.valid and s.is_bang == want_bang:
            tone_passed += 1
        else:
            want = "bằng (ngang/huyền)" if want_bang else "trắc (sắc/hỏi/ngã/nặng)"
            errors.append(PoemError(
                i + 1, "tone",
                f"Câu {i + 1}, tiếng thứ {pos} '{s.text}' mang thanh {TONE_NAMES[s.tone]}, cần thanh {want}.",
                pos, s.text))

    for i in range(n):
        check(i, 2, True)
        check(i, 4, False)
        check(i, 6, True)
        if kinds[i] == "bat":
            check(i, 8, True)
            tone_total += 1
            if line_ok[i]:
                s6, s8 = parsed[i][5], parsed[i][7]
                if {s6.tone, s8.tone} == {"ngang", "huyen"}:
                    tone_passed += 1
                elif s6.is_bang and s8.is_bang:
                    errors.append(PoemError(
                        i + 1, "tone",
                        f"Câu {i + 1}: tiếng thứ 6 '{s6.text}' và tiếng thứ 8 '{s8.text}' cùng thanh {TONE_NAMES[s6.tone]}; "
                        "một tiếng phải là thanh huyền, tiếng kia thanh ngang.",
                        8, s8.text))

    links: list[tuple[int, int, int, int]] = []
    for i in range(0, n - 1, 2):
        links.append((i, 6, i + 1, 6))
        if i + 2 < n:
            links.append((i + 1, 8, i + 2, 6))

    rhyme_sum = 0.0
    for (la, pa, lb, pb) in links:
        if not (line_ok[la] and line_ok[lb]):
            continue
        a, b = parsed[la][pa - 1], parsed[lb][pb - 1]
        credit = rhyme_credit(a, b)
        rhyme_sum += credit
        if credit == 0.0:
            errors.append(PoemError(
                lb + 1, "rhyme",
                f"Vần: tiếng thứ {pb} câu {lb + 1} '{b.text}' (vần {b.rime}) không hiệp vần với "
                f"tiếng thứ {pa} câu {la + 1} '{a.text}' (vần {a.rime}).",
                pb, b.text))
        elif credit < 1.0:
            notes.append(f"Vần thông (chưa chuẩn): '{a.text}' (câu {la + 1}) và '{b.text}' (câu {lb + 1}).")
        elif a.text.lower() == b.text.lower():
            warnings.append(f"Lặp vần: '{a.text}' xuất hiện ở cả hai vị trí gieo vần (câu {la + 1} và {lb + 1}).")

    seen: dict[str, int] = {}
    for i, line in enumerate(lines):
        key = " ".join(_words(line)).lower()
        if key in seen:
            warnings.append(f"Câu {i + 1} lặp lại câu {seen[key] + 1}.")
        seen.setdefault(key, i)

    length_score = length_ok / n
    tone_score = tone_passed / tone_total if tone_total else 0.0
    rhyme_score = rhyme_sum / len(links) if links else 0.0
    score = W_LENGTH * length_score + W_TONE * tone_score + W_RHYME * rhyme_score
    return PoemReport(lines, round(length_score, 4), round(tone_score, 4), round(rhyme_score, 4), round(score, 4), errors, warnings, notes)


if __name__ == "__main__":
    import json
    import sys

    print(json.dumps(evaluate_poem(sys.stdin.read()).to_dict(), ensure_ascii=False, indent=2))
