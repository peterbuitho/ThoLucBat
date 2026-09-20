"""Prompt templates shared by dataset preparation, evaluation, and the agent."""
from __future__ import annotations

import os
import random

SYSTEM_PROMPT = "Bạn là nhà thơ Việt Nam chuyên sáng tác thơ lục bát."

# {n} = number of lines, {topic} = free-text subject
REQUEST_TEMPLATES_WITH_LINES = [
    "Viết một bài thơ lục bát {n} câu về {topic}.",
    "Làm một bài thơ lục bát {n} câu kể về {topic}.",
    "Hãy sáng tác {n} câu lục bát về {topic}.",
    "Viết {n} câu lục bát nói về {topic}.",
]
REQUEST_TEMPLATES = [
    "Viết thơ lục bát về {topic}.",
    "Hãy sáng tác một bài lục bát về {topic}.",
    "Làm thơ lục bát về {topic}.",
    "Cho tôi một bài thơ lục bát về chủ đề {topic}.",
]
TITLE_TEMPLATES = [
    "Viết một bài thơ lục bát với nhan đề “{title}”.",
    "Hãy làm thơ lục bát, đặt tên bài thơ là “{title}”.",
    "Sáng tác một bài lục bát {n} câu có nhan đề “{title}”.",
]
FREE_TEMPLATES = [
    "Viết một bài thơ lục bát {n} câu.",
    "Hãy làm một bài thơ lục bát tùy ý, khoảng {n} câu.",
]


def make_request(topic: str, n_lines: int | None = None) -> str:
    """Canonical user request used by the app (matches training distribution)."""
    topic = topic.strip().rstrip(".")
    if n_lines:
        return REQUEST_TEMPLATES_WITH_LINES[0].format(n=n_lines, topic=topic)
    return REQUEST_TEMPLATES[0].format(topic=topic)


def random_request(rng: random.Random, n_lines: int, title: str | None) -> str:
    """Varied training request. Uses the poem title as the topic signal."""
    if not title:
        return rng.choice(FREE_TEMPLATES).format(n=n_lines)
    r = rng.random()
    if r < 0.35:
        return rng.choice(TITLE_TEMPLATES).format(title=title, n=n_lines)
    if r < 0.7:
        return rng.choice(REQUEST_TEMPLATES_WITH_LINES).format(n=n_lines, topic=title.lower())
    return rng.choice(REQUEST_TEMPLATES).format(topic=title.lower())


def chat(user: str, assistant: str | None = None) -> list[dict]:
    msgs = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    if assistant is not None:
        msgs.append({"role": "assistant", "content": assistant})
    return msgs


def make_repair_request(request: str, poem: str, report) -> str:
    """Ask the model to fix a poem given the validator's report (a PoemReport)."""
    return (
        f"Yêu cầu ban đầu:\n{request}\n\n"
        f"Bài thơ hiện tại:\n{poem}\n\n"
        "Kết quả kiểm tra luật lục bát:\n"
        f"- Số tiếng: {report.length_score:.2f}\n"
        f"- Thanh điệu: {report.tone_score:.2f}\n"
        f"- Gieo vần: {report.rhyme_score:.2f}\n"
        f"- Tổng: {report.score:.2f}\n\n"
        f"Các lỗi cần sửa:\n{report.error_summary()}\n\n"
        "Hãy sửa lại bài thơ cho đúng luật lục bát (câu lục 6 tiếng, câu bát 8 tiếng; "
        "tiếng 2 và 6 thanh bằng, tiếng 4 thanh trắc, tiếng 8 thanh bằng khác dấu với tiếng 6; "
        "tiếng 6 câu lục vần với tiếng 6 câu bát, tiếng 8 câu bát vần với tiếng 6 câu lục kế tiếp).\n"
        "Giữ nguyên chủ đề, hình ảnh chính và cảm xúc, chỉ sửa những chỗ sai.\n"
        "Chỉ trả về bài thơ đã sửa, mỗi câu một dòng, không giải thích."
    )


def render_prompt(request: str, family: str | None = None) -> str:
    """Raw chat prompt (thinking off), identical to the tokenizer's chat template output.

    Needed for line-by-line generation through the /v1/completions endpoint, where we append the
    lines written so far to the assistant turn. Family comes from VIETPOET_FAMILY (qwen | gemma).
    """
    family = family or os.environ.get("VIETPOET_FAMILY", "qwen")
    if family == "gemma":
        # Gemma 4: the tokenizer does not add <bos> itself, so it is part of the text.
        return (
            f"<bos><|turn>system\n{SYSTEM_PROMPT}<turn|>\n"
            f"<|turn>user\n{request}<turn|>\n"
            "<|turn>model\n<|channel>thought\n<channel|>"
        )
    return (
        f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\n{request}<|im_end|>\n"
        "<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )
