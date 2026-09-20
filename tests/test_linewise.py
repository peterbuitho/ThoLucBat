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
        self._use_logprobs = True
        self._logprobs_arg = 1
        self._max_n = None

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


# ---- compatibility with servers other than vLLM (llama.cpp / LM Studio) ----

from types import SimpleNamespace as NS


def test_mean_logprob_vllm_style():
    c = NS(logprobs=NS(token_logprobs=[-1.0, -3.0, None], model_extra={}))
    assert PoetAgent._mean_logprob(c) == -2.0


def test_mean_logprob_llamacpp_style():
    c = NS(logprobs=NS(token_logprobs=None, model_extra={"content": [{"token": "a", "logprob": -0.5}, {"token": "b", "logprob": -1.5}]}))
    assert PoetAgent._mean_logprob(c) == -1.0


def test_mean_logprob_missing_is_none():
    assert PoetAgent._mean_logprob(NS(logprobs=None)) is None
    assert PoetAgent._mean_logprob(NS(logprobs=NS(token_logprobs=None, model_extra={}))) is None


def test_tops_up_with_single_requests_when_server_ignores_n():
    calls = []

    class OneAtATime(FakeAgent):
        _complete_lines = PoetAgent._complete_lines                      # use the real method

        def _completion_choices(self, prompt, n, temperature):
            calls.append(n)
            return [NS(text=f" line{len(calls)} ", logprobs=None)]      # always a single choice, no logprobs

    out = OneAtATime({})._complete_lines("p", 5, 0.9)
    assert len(out) == 5 and calls[0] == 5 and calls[1:] == [1, 1, 1, 1]
    assert all(lp == 0.0 for _, lp in out) and out[0][0] == "line1"      # text stripped, missing logprob -> 0


def test_no_logprobs_still_picks_a_clean_line_and_applies_the_penalty():
    class NoLogprobs(FakeAgent):
        _complete_lines = PoetAgent._complete_lines

        def _completion_choices(self, prompt, n, temperature):
            lines = {0: [KIEU[0]], 1: [KIEU[1]]}[len(self.prompts_lines(prompt))]
            return [NS(text=t, logprobs=None) for t in lines]

    res = NoLogprobs({}).create_poem_linewise("x", 2, candidates=1)
    assert res.poem.splitlines() == KIEU[:2]


import httpx
from openai import BadRequestError


def _bad_request(message):
    return BadRequestError(message, response=httpx.Response(400, request=httpx.Request("POST", "http://x/v1/completions")), body=None)


def _server(create):
    a = FakeAgent({})
    a._complete_lines = lambda *args: PoetAgent._complete_lines(a, *args)
    a._completion_choices = lambda *args: PoetAgent._completion_choices(a, *args)
    a.client, a.model = NS(completions=NS(create=create)), "m"
    return a


def test_learns_the_servers_n_limit_from_the_error_and_splits_the_request():
    seen = []

    def create(**kw):
        seen.append(kw["n"])
        if kw["n"] > 4:
            raise _bad_request("Error code: 400 - {'message': \"Field 'n': Value must be between 1 <= value <= 4, but got 16\"}")
        return NS(choices=[NS(text=f"l{len(seen)}", logprobs=None)] * kw["n"])

    a = _server(create)
    out = a._complete_lines("p", 16, 0.9)
    assert len(out) == 16 and a._max_n == 4
    assert seen[0] == 16 and sorted(seen[1:]) == [4, 4, 4, 4]      # first try fails, then 4 x 4
    assert a._complete_lines("p", 8, 0.9) and max(seen[5:]) == 4   # remembered: never asks for more than 4 again


def test_lm_studio_one_completion_limit_does_not_switch_off_logprobs():
    seen = []

    def create(**kw):
        seen.append((kw["n"], "logprobs" in kw))
        if kw["n"] > 1:
            raise _bad_request("Error code: 400 - {'error': 'LM Studio /v1/completions currently supports only one completion per request.'}")
        return NS(choices=[NS(text="x", logprobs=None)])

    a = _server(create)
    assert len(a._complete_lines("p", 4, 0.9)) == 4
    assert a._max_n == 1 and a._use_logprobs is True
    assert seen[0] == (4, True) and all(s == (1, True) for s in seen[1:])   # one failed try, then 4 x n=1 with logprobs


def test_drops_logprobs_when_the_server_rejects_them():
    seen = []

    def create(**kw):
        seen.append("logprobs" in kw)
        if "logprobs" in kw:
            raise _bad_request("logprobs is not supported")
        return NS(choices=[NS(text="x", logprobs=None)] * kw["n"])

    a = _server(create)
    assert len(a._complete_lines("p", 3, 0.9)) == 3 and a._use_logprobs is False
    assert seen == [True, False]
    a._complete_lines("p", 3, 0.9)
    assert seen[2:] == [False]                                      # not retried with logprobs again


def test_mlx_server_wants_logprobs_true_and_drops_the_connection_on_an_int():
    import httpx
    from openai import APIConnectionError
    seen = []

    def create(**kw):
        seen.append(kw.get("logprobs"))
        if kw.get("logprobs") is not True:
            raise APIConnectionError(request=httpx.Request("POST", "http://x/v1/completions"))
        return NS(choices=[NS(text="x", logprobs=None)])

    a = _server(create)
    assert len(a._complete_lines("p", 1, 0.9)) == 1
    assert seen == [1, True] and a._use_logprobs is True
    a._complete_lines("p", 1, 0.9)
    assert seen[2:] == [True]                                       # remembered


def test_connection_errors_switch_logprobs_off_and_then_propagate():
    import httpx
    import pytest
    from openai import APIConnectionError

    def create(**kw):
        raise APIConnectionError(request=httpx.Request("POST", "http://x/v1/completions"))

    a = _server(create)
    with pytest.raises(APIConnectionError):
        a._complete_lines("p", 1, 0.9)
    assert a._use_logprobs is False
