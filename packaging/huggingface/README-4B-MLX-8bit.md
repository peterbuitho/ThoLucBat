---
license: apache-2.0
language:
- vi
base_model: peterbuitho/VietPoet-Qwen3.5-4B
base_model_relation: quantized
datasets:
- phamson02/vietnamese-poetry-corpus
library_name: mlx
pipeline_tag: text-generation
tags:
- mlx
- vietnamese
- poetry
- luc-bat
---

# VietPoet Qwen3.5-4B (MLX, 8-bit)

[VietPoet-Qwen3.5-4B](https://huggingface.co/peterbuitho/VietPoet-Qwen3.5-4B), a Qwen3.5-4B fine-tuned (QLoRA, 8,000
poems, 2 epochs) to write Vietnamese **lục bát** poems, converted to Apple's [MLX](https://github.com/ml-explore/mlx)
format with `mlx_lm.convert -q --q-bits 8` (8.5 bits per weight, 4.5 GB). It is the near-lossless MLX version; the
[4-bit version](https://huggingface.co/peterbuitho/VietPoet-Qwen3.5-4B-MLX-4bit) is about half the size. For other
systems see the [16-bit weights](https://huggingface.co/peterbuitho/VietPoet-Qwen3.5-4B) and the
[GGUF files](https://huggingface.co/peterbuitho/VietPoet-Qwen3.5-4B-GGUF).

It is meant to be used with the line-by-line sampler and rule checker from
[github.com/peterbuitho/ThoLucBat](https://github.com/peterbuitho/ThoLucBat). The macOS package in that repository
(Apple silicon, LM Studio) sets everything up for you. Used on its own the model writes the right shape but breaks the
tone rules more often.

## What it does and does not do

With the sampler (16 samples per line, only lines that satisfy the 6/8 length, tone and rhyme rules are kept), on 40
held-out "8 câu" prompts served by `mlx_lm.server` on an Apple M2 Pro: rule score **0.992**, **95%** of poems fully
valid (the 16-bit model on vLLM: 0.994 and 98% on 100 prompts). Without the sampler the raw model scores about 0.81 and
breaks the 6th/8th-syllable tone rule in 38% of bát lines.

**These numbers measure form, not poetry.** Poems are correct lục bát but the meaning is often loose or off-topic
(training prompts only had the poem title as topic). Judge the poetry yourself.

## Run it

```bash
pip install mlx-lm
mlx_lm.server --model peterbuitho/VietPoet-Qwen3.5-4B-MLX-8bit --port 8080 --prompt-cache-size 0
```

Then start the page from the GitHub repository against that server:

```bash
VIETPOET_BASE_URL=http://127.0.0.1:8080/v1 VIETPOET_MODEL=default_model python -m app.webui
```

How `mlx_lm.server` (0.31.3) differs from vLLM, and what the sampler does about it:
- `--prompt-cache-size 0` is needed: with the prompt cache on, the server's generation thread crashes (`IndexError`) as
  soon as a prompt exactly matches a cached one, which the line-by-line sampler causes on every line, and every later
  request then hangs.
- The request's `model` must be `default_model` (or the local path). Any other name is treated as a repository to load,
  and the server contacts huggingface.co to fetch it.
- `n` is ignored (always one completion), so the sampler asks for 16 lines with 16 single requests. Keep it to 8 at a
  time: 16 simultaneous connections get reset.
- `logprobs` must be `true`, not a number; an integer makes the server drop the connection.
- The end-of-turn token `<|im_end|>` comes back as text, so the sampler cuts candidate lines at the first special token.

Speed for one 8-line poem with 16 samples per line: about 75 to 85 seconds on an M2 Pro (16 GB) with `mlx_lm.server`.

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
