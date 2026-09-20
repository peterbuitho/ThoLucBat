from pathlib import Path

import pytest

from app.prompts import SYSTEM_PROMPT, chat, render_prompt

MODEL = Path.home() / "vietpoet-models" / "sft-v1" / "merged"


def test_render_prompt_shape():
    p = render_prompt("Viết thơ.")
    assert p.startswith("<|im_start|>system\n") and p.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")
    assert SYSTEM_PROMPT in p


@pytest.mark.skipif(not MODEL.exists(), reason="merged model not present")
def test_render_prompt_matches_tokenizer_chat_template():
    transformers = pytest.importorskip("transformers")
    tok = transformers.AutoTokenizer.from_pretrained(str(MODEL))
    expected = tok.apply_chat_template(chat("Viết thơ."), tokenize=False, add_generation_prompt=True, enable_thinking=False)
    assert render_prompt("Viết thơ.") == expected


def test_render_prompt_gemma_matches_tokenizer_chat_template():
    transformers = pytest.importorskip("transformers")
    try:
        tok = transformers.AutoTokenizer.from_pretrained("unsloth/gemma-4-12b-it")
    except Exception:
        pytest.skip("Gemma 4 tokenizer not available offline")
    expected = tok.apply_chat_template(chat("Viết thơ."), tokenize=False, add_generation_prompt=True, enable_thinking=False)
    assert render_prompt("Viết thơ.", family="gemma") == expected
    assert expected.startswith("<bos>") and expected.count("<bos>") == 1
