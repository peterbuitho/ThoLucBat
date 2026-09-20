import pytest

from app.validator import clean_poem, evaluate_poem, parse_syllable

KIEU = """Trăm năm trong cõi người ta,
Chữ tài chữ mệnh khéo là ghét nhau.
Trải qua một cuộc bể dâu,
Những điều trông thấy mà đau đớn lòng."""


def errors(poem, kind):
    return [e for e in evaluate_poem(poem).errors if e.kind == kind]


def test_kieu_is_valid():
    r = evaluate_poem(KIEU)
    assert r.length_score == 1.0 and r.tone_score == 1.0
    assert r.valid and r.score >= 0.95
    assert not r.errors


@pytest.mark.parametrize("word,tone,rime", [
    ("quê", "ngang", "ê"), ("gì", "huyen", "i"), ("hoa", "ngang", "a"), ("thuỷ", "hoi", "i"),
    ("mệnh", "nang", "ênh"), ("cõi", "nga", "oi"), ("khéo", "sac", "eo"), ("nghiêng", "ngang", "iêng"),
])
def test_parse_syllable(word, tone, rime):
    s = parse_syllable(word)
    assert s.valid and s.tone == tone and s.rime == rime


def test_non_vietnamese_token_is_invalid():
    assert not parse_syllable("wifi").valid


def test_wrong_length_detected():
    poem = KIEU.replace("Trăm năm trong cõi người ta", "Trăm năm trong cõi người")
    e = errors(poem, "length")
    assert len(e) == 1 and e[0].line == 1


def test_tone_position_2_must_be_bang():
    poem = KIEU.replace("Trăm năm", "Trăm nấm")
    e = [x for x in errors(poem, "tone") if x.line == 1 and x.pos == 2]
    assert e


def test_tone_position_4_must_be_trac():
    poem = KIEU.replace("Trải qua một cuộc bể dâu", "Trải qua một cùng bể dâu")
    assert [x for x in errors(poem, "tone") if x.line == 3 and x.pos == 4]


def test_sixth_and_eighth_must_differ_in_bang_tone():
    poem = KIEU.replace("khéo là ghét nhau", "khéo là ghét nhàu")
    e = errors(poem, "tone")
    assert any(x.line == 2 and "cùng thanh" in x.message for x in e)


def test_rhyme_mismatch_detected():
    poem = KIEU.replace("Trải qua một cuộc bể dâu", "Trải qua một cuộc bể xuân")
    assert errors(poem, "rhyme")


def test_near_rhyme_is_a_note_not_an_error():
    r = evaluate_poem(KIEU)
    assert any("dâu" in n for n in r.notes) and not r.errors


def test_duplicate_line_is_a_warning_and_blocks_valid():
    poem = KIEU + "\n" + KIEU.splitlines()[0] + "\n" + KIEU.splitlines()[1]
    r = evaluate_poem(poem)
    assert any("lặp lại" in w for w in r.warnings) and not r.valid


def test_odd_number_of_lines_warns():
    r = evaluate_poem("\n".join(KIEU.splitlines()[:3]))
    assert any("số lẻ" in w for w in r.warnings) and not r.valid


def test_empty_poem():
    assert evaluate_poem("").score == 0.0


def test_score_weights():
    r = evaluate_poem(KIEU)
    assert r.score == pytest.approx(0.1 * r.length_score + 0.3 * r.tone_score + 0.6 * r.rhyme_score, abs=1e-3)


def test_clean_poem_strips_markdown_and_numbering():
    raw = "```\n1. **Trăm năm trong cõi người ta,**\n- Chữ tài chữ mệnh khéo là ghét nhau.\n\n```"
    assert clean_poem(raw) == ["Trăm năm trong cõi người ta,", "Chữ tài chữ mệnh khéo là ghét nhau."]
