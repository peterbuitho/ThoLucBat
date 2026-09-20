"""Gradio front-end. Run: python -m app.webui   (binds 127.0.0.1:7860)

Optional auth: set VIETPOET_USER and VIETPOET_PASS (required if tunnelled publicly).
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

import gradio as gr

from .agent import PoetAgent

DATA = Path(__file__).resolve().parent.parent / "data"
LOG = DATA / "generations.jsonl"
FEEDBACK = DATA / "feedback.jsonl"

agent = PoetAgent()


def _append(path: Path, rec: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def make_poem(topic: str, n_lines: int):
    topic = (topic or "").strip()
    if not topic:
        raise gr.Error("Hãy nhập chủ đề.")
    res = agent.create_poem_linewise(topic, int(n_lines))
    r = res.report
    rec = {"id": uuid.uuid4().hex[:12], "ts": time.time(), "topic": topic, "n_lines": int(n_lines),
           "poem": res.poem, "rounds": res.rounds, "score": r.score, "length": r.length_score,
           "tone": r.tone_score, "rhyme": r.rhyme_score, "valid": r.valid, "history": res.history}
    _append(LOG, rec)
    detail = (f"**Điểm luật: {r.score:.2f}** — số tiếng {r.length_score:.2f} · thanh điệu {r.tone_score:.2f} · "
              f"vần {r.rhyme_score:.2f} · số câu thử: {sum(h['sampled'] for h in res.history)}")
    if r.errors or r.warnings:
        detail += "\n\nCòn lỗi:\n" + r.error_summary()
    return res.poem, detail, rec, ""


def rate(rec: dict | None, value: int):
    if not rec:
        return "Chưa có bài thơ."
    _append(FEEDBACK, {"id": rec["id"], "topic": rec["topic"], "poem": rec["poem"],
                       "score": rec["score"], "rating": value, "ts": time.time()})
    return "Cảm ơn bạn đã đánh giá!"


with gr.Blocks(title="VietPoet") as demo:
    gr.Markdown("# VietPoet — thơ lục bát")
    with gr.Row():
        topic = gr.Textbox(label="Chủ đề", placeholder="Nỗi nhớ quê khi sống ở nước ngoài", scale=4)
        n_lines = gr.Slider(4, 16, value=8, step=2, label="Số câu")
    go = gr.Button("Làm thơ", variant="primary")
    poem = gr.Textbox(label="Bài thơ", lines=10, interactive=False)
    detail = gr.Markdown()
    state = gr.State()
    with gr.Row():
        up = gr.Button("👍")
        down = gr.Button("👎")
    thanks = gr.Markdown()
    go.click(make_poem, [topic, n_lines], [poem, detail, state, thanks])
    topic.submit(make_poem, [topic, n_lines], [poem, detail, state, thanks])
    up.click(lambda s: rate(s, 1), state, thanks)
    down.click(lambda s: rate(s, -1), state, thanks)

if __name__ == "__main__":
    user, pw = os.environ.get("VIETPOET_USER"), os.environ.get("VIETPOET_PASS")
    demo.queue(default_concurrency_limit=2).launch(
        server_name="127.0.0.1", server_port=7860, auth=(user, pw) if user and pw else None)
