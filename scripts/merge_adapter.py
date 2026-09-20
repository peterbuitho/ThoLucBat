"""Merge a LoRA adapter into 16-bit weights. Output goes to /home (keeps 9GB of weights off the NTFS repo).

  ~/.unsloth/studio/unsloth_studio/bin/python scripts/merge_adapter.py sft-v1
"""
import sys
from pathlib import Path

import shutil

from unsloth import FastLanguageModel

# HF cache blobs are read-only (0444); Unsloth copies them then overwrites in place.
shutil.copymode = lambda *a, **k: None
shutil.copystat = lambda *a, **k: None

name = sys.argv[1]
adapter = Path(__file__).resolve().parent.parent / "models" / name / "adapter"
out = Path.home() / "vietpoet-models" / name / "merged"
model, tok = FastLanguageModel.from_pretrained(str(adapter), max_seq_length=1024, load_in_4bit=True)
model.save_pretrained_merged(str(out), tok, save_method="merged_16bit")
print("MERGED ->", out)
