"""Gradio front-end. Run: python -m app.webui   (binds 127.0.0.1:7860)

Home network (LAN) use:
  VIETPOET_HOST=<this machine's LAN address> python -m app.webui
  VIETPOET_ALLOW_SWITCH=1 ...     adds a model switcher (off by default; see app/serving.py for its safety rules)
The page talks only to the local vLLM server; nothing here contacts the internet (Gradio analytics are off).
"""
from __future__ import annotations

import os

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import json
import time
import uuid
from pathlib import Path

import gradio as gr

from . import serving
from .agent import PoetAgent

DATA = Path(__file__).resolve().parent.parent / "data"
LOG = DATA / "generations.jsonl"
FEEDBACK = DATA / "feedback.jsonl"
ALLOW_SWITCH = os.environ.get("VIETPOET_ALLOW_SWITCH") == "1"

agent = PoetAgent()


def _append(path: Path, rec: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def make_poem(topic: str, n_lines: int):
    topic = (topic or "").strip()
    if not topic:
        raise gr.Error("Hãy nhập chủ đề.")
    if serving.is_switching():
        raise gr.Error("Đang đổi mô hình, vui lòng đợi một chút rồi thử lại.")
    if _sync_family() is None:
        raise gr.Error("Chưa có mô hình nào đang chạy." + (" Hãy mở mục Mô hình và chọn một mô hình." if ALLOW_SWITCH else ""))
    res = agent.create_poem_linewise(topic, int(n_lines))
    r = res.report
    rec = {"id": uuid.uuid4().hex[:12], "ts": time.time(), "topic": topic, "n_lines": int(n_lines),
           "poem": res.poem, "rounds": res.rounds, "score": r.score, "length": r.length_score,
           "tone": r.tone_score, "rhyme": r.rhyme_score, "valid": r.valid, "history": res.history,
           "model": serving.current_key()}
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
                       "score": rec["score"], "rating": value, "model": rec.get("model"), "ts": time.time()})
    return "Cảm ơn bạn đã đánh giá!"


# ---- model switcher (home use only, opt-in) ---------------------------------------------------

def _sync_family() -> str | None:
    """Point the agent at the right raw-prompt format for whatever model the server is running."""
    key = serving.current_key()
    if key in serving.MODELS:
        agent.family = serving.MODELS[key]["family"]
    return key


def _status(key: str | None) -> str:
    if key in serving.MODELS:
        return f"Đang chạy: **{serving.MODELS[key]['label']}**"
    return "Đang chạy: mô hình khác" if key == "other" else "Chưa có mô hình nào đang chạy. Chọn một mô hình rồi bấm đổi."


def load_state():
    key = _sync_family()
    return (gr.update(value=key if key in serving.MODELS else None), _status(key)) if ALLOW_SWITCH else (None, "")


def _check_home(request: gr.Request) -> None:
    client = request.client.host if request.client else ""
    if not ALLOW_SWITCH or not serving.is_home_request(client, dict(request.headers)):
        raise gr.Error("Chỉ điều khiển được mô hình từ mạng nhà.")


def do_switch(key: str | None, request: gr.Request):
    _check_home(request)
    if key not in serving.available():
        raise gr.Error("Hãy chọn một mô hình.")
    label, minutes = serving.MODELS[key]["label"], serving.MODELS[key]["minutes"]
    busy = gr.update(interactive=False)
    wait = (f"⏳ **Đang đổi sang {label}.** Việc này mất khoảng {minutes} phút (dừng mô hình cũ, nạp mô hình mới vào GPU). "
            "Vui lòng đợi và đừng đóng trang; các nút sẽ bật lại khi xong.")
    yield wait, busy, busy, busy, busy
    try:
        for done, msg in serving.switch(key):
            yield f"{wait}\n\n`{msg}`", busy, busy, busy, busy
    except (ValueError, RuntimeError, TimeoutError) as e:
        on = gr.update(interactive=True)
        yield f"❌ Không đổi được mô hình: {e}", on, on, on, on
        return
    on = gr.update(interactive=True)
    yield _status(_sync_family()) + " ✅ Đã sẵn sàng.", on, on, on, gr.update(value=key, interactive=True)


def do_stop(request: gr.Request):
    _check_home(request)
    busy, on = gr.update(interactive=False), gr.update(interactive=True)
    wait = "⏳ **Đang tắt mô hình** và giải phóng GPU. Việc này mất vài giây đến nửa phút, vui lòng đợi."
    yield wait, busy, busy, busy, busy
    try:
        for done, msg in serving.stop():
            yield f"{wait}\n\n`{msg}`", busy, busy, busy, busy
    except (RuntimeError, TimeoutError) as e:
        yield f"❌ Không tắt được mô hình: {e}", on, on, on, on
        return
    yield "✅ Đã tắt mô hình, GPU đã được giải phóng. Chọn một mô hình để bật lại.", on, on, on, gr.update(value=None, interactive=True)


with gr.Blocks(title="VietPoet", analytics_enabled=False) as demo:
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

    if ALLOW_SWITCH:
        with gr.Accordion("Mô hình (chỉ dùng trong mạng nhà)", open=False):
            model_dd = gr.Dropdown([(m["label"], k) for k, m in serving.available().items()], label="Mô hình", value=None)
            with gr.Row():
                switch_btn = gr.Button("Đổi mô hình")
                stop_btn = gr.Button("Tắt mô hình")
            model_status = gr.Markdown()
        controls = [model_status, go, switch_btn, stop_btn, model_dd]
        switch_btn.click(do_switch, model_dd, controls, api_name="switch")
        stop_btn.click(do_stop, None, controls, api_name="stop")
        demo.load(load_state, None, [model_dd, model_status])
    else:
        demo.load(lambda: _sync_family() and None)

if __name__ == "__main__":
    user, pw = os.environ.get("VIETPOET_USER"), os.environ.get("VIETPOET_PASS")
    host = os.environ.get("VIETPOET_HOST", "127.0.0.1")
    demo.queue(default_concurrency_limit=2).launch(
        server_name=host, server_port=int(os.environ.get("VIETPOET_PORT", "7860")),
        auth=(user, pw) if user and pw else None, share=False)
