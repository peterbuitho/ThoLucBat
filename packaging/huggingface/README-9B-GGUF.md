---
license: apache-2.0
language:
- vi
base_model: Qwen/Qwen3.5-9B
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

# VietPoet Qwen3.5-9B (GGUF)

A Qwen3.5-9B fine-tuned (QLoRA, 8,000 poems, 2 epochs) to write Vietnamese **lục bát** poems, exported for
LM Studio / llama.cpp. It is meant to be used with the line-by-line sampler and rule checker from
[github.com/peterbuitho/ThoLucBat](https://github.com/peterbuitho/ThoLucBat), which the friends' package
(`VietPoet-win.zip`) sets up for you. Used on its own it writes the right shape but breaks the tone rules more often.

| File | Size | Notes |
|---|---|---|
| `VietPoet-Qwen3.5-9B-Q8_0.gguf` | 9.8 GB | near-lossless; needs a large graphics card (the file alone is 9.8 GB) |
| `VietPoet-Qwen3.5-9B-Q4_K_M.gguf` | 5.8 GB | smaller; for graphics cards with less memory |

## What it does and does not do

The larger sibling of [VietPoet-Qwen3.5-4B-GGUF](https://huggingface.co/peterbuitho/VietPoet-Qwen3.5-4B-GGUF), trained the
same way. In the author's tests (16-bit model on vLLM, 100 held-out "8 câu" prompts, line-by-line sampler with 16 samples per
line) the 9B and the 4B are equivalent on the rules: rule score 0.994, 98% of poems fully valid. The raw 9B breaks the
6th/8th-syllable tone rule far less often than the 4B does (10% vs 38% of bát lines), so it needs the sampler less, but
with the sampler the difference disappears. **These GGUF files were not separately scored**, and the 9B is slower and needs
more memory than the 4B. Whether it writes *better poems* is not something these numbers can say.

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
* Base model: [Qwen/Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) (Apache-2.0).
* Scoring idea: Vietnamese Poem Generation & the Prospect of Cross-Language Poem-to-Poem Translation
  ([arXiv:2401.01078](https://arxiv.org/abs/2401.01078)).
