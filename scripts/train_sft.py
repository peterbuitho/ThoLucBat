"""Headless QLoRA SFT with Unsloth. Run with the Unsloth env python:

  ~/.unsloth/studio/unsloth_studio/bin/python scripts/train_sft.py --name sft-v1

Writes:
  runs/<name>/train_config.json   all parameters (+ package versions) - tracked in git
  runs/<name>/log_history.json    loss/eval curves
  models/<name>/adapter           LoRA adapter
  (then) scripts/merge_adapter.py <name>  -> ~/vietpoet-models/<name>/merged for vLLM
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from importlib.metadata import version
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
ROOT = Path(__file__).resolve().parent.parent

ap = argparse.ArgumentParser()
ap.add_argument("--name", required=True)
ap.add_argument("--base-model", default="unsloth/Qwen3.5-4B")
ap.add_argument("--end-token", default="<|im_end|>", help='end-of-turn token appended to the poem (Gemma 4: "<turn|>")')
ap.add_argument("--train", type=Path, default=ROOT / "data/train.jsonl")
ap.add_argument("--val", type=Path, default=ROOT / "data/validation.jsonl")
ap.add_argument("--max-seq-length", type=int, default=1024)
ap.add_argument("--load-in-4bit", type=int, default=1)
ap.add_argument("--lora-r", type=int, default=16)
ap.add_argument("--lora-alpha", type=int, default=16)
ap.add_argument("--lora-dropout", type=float, default=0.0)
ap.add_argument("--lr", type=float, default=2e-4)
ap.add_argument("--epochs", type=float, default=2)
ap.add_argument("--batch-size", type=int, default=2)
ap.add_argument("--grad-accum", type=int, default=4)
ap.add_argument("--optim", default="adamw_8bit")
ap.add_argument("--warmup-ratio", type=float, default=0.03)
ap.add_argument("--weight-decay", type=float, default=0.01)
ap.add_argument("--lr-scheduler", default="linear")
ap.add_argument("--eval-samples", type=int, default=100)
ap.add_argument("--eval-steps", type=int, default=200)
ap.add_argument("--save-steps", type=int, default=500)
ap.add_argument("--max-steps", type=int, default=-1, help="smoke tests")
ap.add_argument("--seed", type=int, default=3407)
ap.add_argument("--merge", action="store_true", help="broken on read-only HF blobs; use scripts/merge_adapter.py")
args = ap.parse_args()

run_dir, model_dir = ROOT / "runs" / args.name, ROOT / "models" / args.name
run_dir.mkdir(parents=True, exist_ok=True)

from unsloth import FastLanguageModel  # noqa: E402  (must import before trl/transformers)
from datasets import Dataset  # noqa: E402
from trl import SFTConfig, SFTTrainer  # noqa: E402

TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
cfg = {**{k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
       "target_modules": TARGET_MODULES,
       "versions": {p: version(p) for p in ("unsloth", "unsloth_zoo", "trl", "peft", "transformers", "torch", "bitsandbytes")}}
(run_dir / "train_config.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
print(json.dumps(cfg, indent=2, ensure_ascii=False), flush=True)

model, tok = FastLanguageModel.from_pretrained(
    args.base_model, max_seq_length=args.max_seq_length, load_in_4bit=bool(args.load_in_4bit), dtype=None)
text_tok = getattr(tok, "tokenizer", tok)
model = FastLanguageModel.get_peft_model(
    model, r=args.lora_r, lora_alpha=args.lora_alpha, lora_dropout=args.lora_dropout, bias="none",
    target_modules=TARGET_MODULES, use_gradient_checkpointing="unsloth", random_state=args.seed)


def to_row(line: str) -> dict:
    msgs = json.loads(line)["messages"]
    prompt = text_tok.apply_chat_template(msgs[:-1], tokenize=False, add_generation_prompt=True, enable_thinking=False)
    return {"prompt": prompt, "completion": msgs[-1]["content"] + args.end_token + "\n"}


def load(path: Path, limit: int = 0) -> Dataset:
    rows = [to_row(l) for l in open(path, encoding="utf-8") if l.strip()]
    return Dataset.from_list(rows[:limit] if limit else rows)


train_ds, val_ds = load(args.train), load(args.val, args.eval_samples)
print("SAMPLE PROMPT:\n" + train_ds[0]["prompt"] + "\nSAMPLE COMPLETION:\n" + train_ds[0]["completion"], flush=True)

trainer = SFTTrainer(
    model=model, processing_class=text_tok, train_dataset=train_ds, eval_dataset=val_ds,
    args=SFTConfig(
        output_dir=str(model_dir / "checkpoints"), max_length=args.max_seq_length,
        per_device_train_batch_size=args.batch_size, per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum, num_train_epochs=args.epochs, max_steps=args.max_steps,
        learning_rate=args.lr, lr_scheduler_type=args.lr_scheduler, warmup_ratio=args.warmup_ratio,
        weight_decay=args.weight_decay, optim=args.optim, seed=args.seed, bf16=True,
        logging_steps=10, eval_strategy="steps", eval_steps=args.eval_steps,
        save_strategy="steps", save_steps=args.save_steps, save_total_limit=2, report_to="none",
        completion_only_loss=True, dataset_num_proc=1))
ids = trainer.train_dataset[0]["input_ids"]
print("FIRST TOKENS:", ids[:8], "| bos count:", ids.count(text_tok.bos_token_id) if text_tok.bos_token_id is not None else "n/a",
      "| last tokens:", text_tok.convert_ids_to_tokens(ids[-4:]), flush=True)
trainer.train()

(run_dir / "log_history.json").write_text(json.dumps(trainer.state.log_history, indent=1))
model.save_pretrained(str(model_dir / "adapter"))
text_tok.save_pretrained(str(model_dir / "adapter"))
if args.merge:
    model.save_pretrained_merged(str(model_dir / "merged"), tok, save_method="merged_16bit")
print("DONE", flush=True)
