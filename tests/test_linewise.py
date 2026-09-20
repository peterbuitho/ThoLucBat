"""Sampler logic tested with a scripted fake model (no server needed)."""
from app.agent import PoetAgent

KIEU = [
    "Trăm năm trong cõi người ta",
    "Chữ tài chữ mệnh khéo là ghét nhau",
    "Trải qua một cuộc bể dâu",
    "Những điều trông thấy mà đau đớn lòng",
]
BAD_LENGTH = "Trăm năm trong cõi người"
BAD_TONE = "Trăm nấm trong cõi người ta"           # tiếng 2 is sắc
BAD_RHYME_L3 = "Trải qua một cuộc bể xuân"           # does not rhyme with "nhau"


class FakeAgent(PoetAgent):
    def __init__(self, script):
        self.script, self.calls, self.prompts = script, 0, []
        self.temperature = 0.9
        self.family = "qwen"

    def _complete_lines(self, prompt, n, temperature):
        self.prompts.append(prompt)
        pool = self.script[len(self.prompts_lines(prompt))] if callable(self.script) is False else self.script(prompt)
        self.calls += 1
        return pool

    @staticmethod
    def prompts_lines(prompt):
        body = prompt.split("</think>\n\n", 1)[1]
        return [l for l in body.split("\n") if l]


def test_picks_the_rule_abiding_line_even_when_a_bad_one_is_more_fluent():
    script = {
        0: [(BAD_TONE, -0.1), (BAD_LENGTH, -0.1), (KIEU[0], -2.0)],
        1: [("Chữ tài chữ mệnh khéo là ghét nhàu", -0.1), (KIEU[1], -1.5)],
        2: [(BAD_RHYME_L3, -0.1), (KIEU[2], -1.0)],
        3: [(KIEU[3], -1.0), ("Những điều trông thấy mà đau đớn tim", -3.0)],
    }
    agent = FakeAgent(script)
    res = agent.create_poem_linewise("nhớ mẹ", 4, candidates=3)
    assert res.poem.splitlines() == KIEU
    assert res.report.valid
    assert all(h["violations"] == 0 for h in res.history)


def test_among_clean_candidates_the_highest_logprob_wins():
    alt = "Chữ tài chữ mệnh khéo là ghét thay"        # also clean for line 2 (8th has no rhyme constraint yet)
    script = {0: [(KIEU[0], -1.0)], 1: [(KIEU[1], -2.0), (alt, -0.5)]}
    res = FakeAgent(script).create_poem_linewise("x", 2, candidates=2)
    assert res.poem.splitlines()[1] == alt


def test_prompt_contains_previous_lines_in_order():
    script = {0: [(KIEU[0], -1)], 1: [(KIEU[1], -1)], 2: [(KIEU[2], -1)]}
    agent = FakeAgent(script)
    agent.create_poem_linewise("x", 3, candidates=1)
    assert agent.prompts_lines(agent.prompts[2]) == KIEU[:2]
    assert agent.prompts[0].endswith("</think>\n\n")


def test_falls_back_to_fewest_violations_after_extra_rounds():
    one = "Trăm nấm trong cõi người ta"                 # 1 violation
    two = "Trăm nấm trong cõi người tà"                 # tone pos2 only too, same -> use a 2-violation line
    worse = "Trăm nấm trong cùng người ta"              # pos2 and pos4 wrong
    agent = FakeAgent({0: [(worse, -0.1), (one, -5.0)]})
    res = agent.create_poem_linewise("x", 1, candidates=2, max_extra_rounds=2)
    assert res.poem == one
    assert agent.calls == 3                               # 1 + max_extra_rounds
    assert res.history[0]["violations"] == 1 and res.history[0]["clean_candidates"] == 0


def test_stops_asking_once_a_clean_candidate_exists():
    agent = FakeAgent({0: [(KIEU[0], -1.0)]})
    agent.create_poem_linewise("x", 1, candidates=1, max_extra_rounds=5)
    assert agent.calls == 1


def test_empty_and_overlong_candidates_are_rejected():
    agent = FakeAgent({0: [("", -0.0), ("a b c d e f g h i", -0.0), (KIEU[0], -3.0)]})
    assert agent.create_poem_linewise("x", 1, candidates=3).poem == KIEU[0]


def test_does_not_repeat_an_earlier_line():
    script = lambda prompt: {0: [(KIEU[0], -1)], 1: [(KIEU[1], -1)], 2: [(KIEU[0], -0.1), (KIEU[2], -2)]}[len(FakeAgent.prompts_lines(prompt))]
    res = FakeAgent(script).create_poem_linewise("x", 3, candidates=2)
    assert res.poem.splitlines() == KIEU[:3]


def test_repeated_rhyme_word_counts_as_violation():
    lines = ["Trăm năm trong cõi người ta"]
    ok = "Chữ tài chữ mệnh khéo là ghét nhau"          # clean: rhymes with "ta" but is a different word
    repeat = "Chữ tài chữ mệnh khéo ta ghét nhàu"       # clean except that its rhyme word is "ta" again
    assert PoetAgent._violations(lines, ok) == 0
    assert PoetAgent._violations(lines, repeat) == 1


def test_repetition_penalty_prefers_fresh_wording():
    prefix = ["Mùa thu ở phố hà thành"]
    fresh = "Nhớ ai nhớ cả cho anh nhớ nàng"
    stale = "Mùa thu nhớ lắm thu xanh nhớ nàng"
    assert PoetAgent._repeat_penalty(prefix, fresh) == 0
    assert PoetAgent._repeat_penalty(prefix, stale) >= 1.0   # same opening words


FRESH = "Nhớ ai nhớ cả cho anh nhớ nàng"
STALE = "Mùa thu nhớ lắm thu xanh nhớ nàng"           # legal, but repeats the opening "Mùa thu"
TOO_LONG = "Mùa thu ở phố hà thành xưa nay xa"
LINE2_POOL = [(TOO_LONG, -0.2), (STALE, -0.9), (FRESH, -1.4)]


def test_all_three_second_line_candidates_are_as_intended():
    first = ["Mùa thu ở phố hà thành"]
    assert PoetAgent._violations(first, FRESH) == 0
    assert PoetAgent._violations(first, STALE) == 0
    assert PoetAgent._violations(first, TOO_LONG) >= 1


def test_penalty_changes_the_choice_among_legal_lines_but_never_picks_an_illegal_one():
    script = {0: [("Mùa thu ở phố hà thành", -1.0)], 1: LINE2_POOL}
    with_pen = FakeAgent(script).create_poem_linewise("x", 2, candidates=3, rep_penalty=1.0)
    no_pen = FakeAgent(script).create_poem_linewise("x", 2, candidates=3, rep_penalty=0.0)
    assert with_pen.poem.splitlines()[1] == FRESH
    assert no_pen.poem.splitlines()[1] == STALE          # most probable legal line; TOO_LONG is never chosen
