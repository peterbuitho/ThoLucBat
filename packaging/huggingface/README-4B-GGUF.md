---
license: apache-2.0
language:
- vi
base_model: Qwen/Qwen3.5-4B
datasets:
- phamson02/vietnamese-poetry-corpus
tags:
- gguf
- lm-studio
- llama.cpp
- vietnamese
- poetry
- luc-bat
---

# VietPoet Qwen3.5-4B (GGUF)

A Qwen3.5-4B fine-tuned (QLoRA, 8,000 poems, 2 epochs) to write Vietnamese **lục bát** poems, exported for
LM Studio / llama.cpp. It is meant to be used with the line-by-line sampler and rule checker from
[github.com/peterbuitho/ThoLucBat](https://github.com/peterbuitho/ThoLucBat), which the friends' package
(`VietPoet-win.zip`) sets up for you. Used on its own it writes the right shape but breaks the tone rules more often.

| File | Size | Notes |
|---|---|---|
| `VietPoet-Qwen3.5-4B-Q8_0.gguf` | 4.6 GB | near-lossless; use with 10 GB+ of graphics memory |
| `VietPoet-Qwen3.5-4B-Q4_K_M.gguf` | 2.8 GB | for smaller graphics cards or CPU |

## What it does and does not do

With the sampler (16 samples per line, only lines that satisfy the 6/8 length, tone and rhyme rules are kept), on 40
held-out "8 câu" prompts against LM Studio: rule score 0.991 (Q8_0), 95% of poems fully valid; Q4_K_M with 4 samples per
line: 0.982, 87.5% valid. Without the sampler the raw model scores about 0.81 and breaks the 6th/8th-syllable tone rule in
38% of bát lines.

**These numbers measure form, not poetry.** Poems are correct lục bát but the meaning is often loose or off-topic
(training prompts only had the poem title as topic). Judge the poetry yourself.

## Prompt format

Qwen chat format with thinking off, and the poem written by appending lines to the assistant turn:

```
<|im_start|>system
Bạn là nhà thơ Việt Nam chuyên sáng tác thơ lục bát.<|im_end|>
<|im_start|>user
Viết một bài thơ lục bát 8 câu về mùa thu quê em.<|im_end|>
<|im_start|>assistant
<think>

</think>

```

The request wording varies (several templates); they are in `app/prompts.py` in the GitHub repo.

## Credits

* Training data: [phamson02/vietnamese-poetry-corpus](https://huggingface.co/datasets/phamson02/vietnamese-poetry-corpus)
  (CC BY 4.0), filtered to poems that pass a lục bát rule checker.
* Base model: [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) (Apache-2.0).
* Scoring idea: Vietnamese Poem Generation & the Prospect of Cross-Language Poem-to-Poem Translation
  ([arXiv:2401.01078](https://arxiv.org/abs/2401.01078)).
