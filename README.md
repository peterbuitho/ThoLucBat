# VietPoet — a lục-bát poet: small LLM + rule checker + repair loop

A local system that writes Vietnamese **lục-bát** poems. A fine-tuned 4B model writes,
an ordinary Python validator checks the 6/8 structure, tone and rhyme, and the model is
asked to repair its own mistakes. Everything ran on one RTX 4090 (24 GB).

```
prompt -> fine-tuned Qwen3.5-4B -> 4 candidate poems -> lục-bát validator
              ^                                            |
              |                 not valid?  <--------------+
              +---- "here is what's wrong, fix it" (max 4 rounds, keep best)
```

The scoring follows the length/tone/rhyme idea of the paper
[Vietnamese Poem Generation & the Prospect of Cross-Language Poem-to-Poem Translation
(arXiv:2401.01078)](https://arxiv.org/abs/2401.01078): `score = 0.1·length + 0.3·tone + 0.6·rhyme`.

## Install and run

The poet is a small web page ([app/webui.py](app/webui.py)) that writes poems with the line-by-line sampler, shows the rule
scores, and logs each poem and thumbs up/down (`data/generations.jsonl`, `data/feedback.jsonl`, git-ignored). It talks only to
a model server on the same machine and nothing is sent to the internet (Gradio analytics are off). Pick your system:
[Windows](#windows-lm-studio) runs the GGUF models in LM Studio, [Linux](#linux-vllm) runs the 16-bit models in vLLM, and
[other servers](#other-servers-llamacpp-and-any-openai-compatible-api) covers llama.cpp and anything OpenAI-compatible.

### Windows (LM Studio)

Run the poet on your own computer with [LM Studio](https://lmstudio.ai). No Python, Linux or command line needed;
nothing you type leaves the machine.

1. Install LM Studio, open it once, then close it.
2. Download `VietPoet-win.zip` from the [latest release](https://github.com/peterbuitho/ThoLucBat/releases/latest)
   and unzip it anywhere (not inside "Program Files").
3. Double-click **Start VietPoet.bat**.

The first start asks which model to use, **4B** (faster, recommended) or **9B**, and whether to run it on the
**graphics card** or the **CPU**. It reads your free graphics memory and, if your choice does not fit, offers a smaller
setup or the CPU. It then downloads the model (3 to 10 GB, once) from Hugging Face
([4B](https://huggingface.co/peterbuitho/VietPoet-Qwen3.5-4B-GGUF), [9B](https://huggingface.co/peterbuitho/VietPoet-Qwen3.5-9B-GGUF)),
loads it into LM Studio and opens the poem page at `http://127.0.0.1:7860`. Later starts take seconds. To choose again, run
**Change model or hardware.bat**. Closing the window stops the page and unloads the model.

What the launcher picks (graphics memory measured with LM Studio on an RTX 4090; seconds are for one 8-line poem):

| Model | File | Graphics memory | Seconds per poem |
|---|---|---|---|
| 4B | `Q8_0` | 5.0 to 6.1 GB | 5 to 14 |
| 4B | `Q4_K_M` | 3.4 to 4.4 GB | 5 to 12 |
| 9B | `Q8_0` | 8.9 to 9.9 GB | 6 to 12 |
| 9B | `Q4_K_M` | 5.6 to 6.7 GB | 5 to 12 |
| 4B / 9B on CPU | `Q4_K_M` | none | about 15 / 25 (fast desktop; slower machines take longer) |

Notes:
- Windows 10/11 only for now. NVIDIA cards are measured automatically; AMD and Intel cards can be tried, or use the CPU.
- Tested on one machine (Windows 11, RTX 4090, LM Studio 0.4.25); other setups are unverified.
- Build the zip yourself with `python scripts/build_package.py`; the launcher is `packaging/windows/start.ps1`.
  Manual alternative without the launcher: `scripts/run_lmstudio.bat` (create a venv first: `py -m venv .venv-win`, then
  `.venv-win\Scripts\pip install -r requirements.txt`, and load a GGUF in LM Studio yourself).

How LM Studio differs from the other servers, and what the launcher does about it:
- `/v1/completions` rejects `n` above 1 ("supports only one completion per request"), so each line takes 16 separate
  requests. The launcher loads the model with `--parallel 16` (fewer on smaller cards) to keep them concurrent.
- It never returns log-probabilities (`logprobs` is accepted and answered with `null`), so the sampler cannot rank
  candidates by fluency and picks by rule violations and the repetition penalty only.
- Its default speculative decoding accepted about 1 draft token in 20 and crashed the CUDA engine at 16 parallel requests
  with `Q4_K_M`, so the launcher turns it off (`--no-speculative-draft-mtp`).

On 40 prompts against LM Studio the 4B `Q8_0` scored 0.991 with 95% of poems fully valid; the 4B `Q4_K_M` with 4
candidates per line scored 0.982 with 87.5% valid (the 16-bit model on vLLM: 0.994 and 98%, on 100 prompts).

### Linux (vLLM)

Needs a GPU and the merged 16-bit models made by the [Reproduce](#reproduce) steps (they are not published; only the GGUF
exports are). vLLM listens on 127.0.0.1 only, and telemetry is off (`VLLM_NO_USAGE_STATS`, `DO_NOT_TRACK`, `HF_HUB_OFFLINE`
for local models). Start and stop everything with one script (the model server plus the page):

```bash
scripts/poet.sh start [4b|9b|gemma] [--lan]   # load the model (default 4b), then start the page
scripts/poet.sh stop                          # stop the page and shut vLLM down, freeing the GPU
scripts/poet.sh status                        # what is running, and the page address
```

The page listens on this machine only (`http://127.0.0.1:7860`); `--lan` binds it to the machine's home-network
address instead (refused unless that address is private), so phones and laptops at home can use it.

Switching between the 4B, 9B and Gemma 4 models (only one fits on the GPU at a time):

```bash
scripts/switch_model.sh list              # which models exist, which one is running
scripts/switch_model.sh 9b                # stop the current one, load this one, wait until ready (~1 min)
scripts/switch_model.sh stop              # shut vLLM down and free the GPU (e.g. before training)
VIETPOET_ALLOW_SWITCH=1 VIETPOET_HOST=<lan-address> .venv/bin/python -m app.webui   # page with a model dropdown
```

The page's model section (dropdown plus "stop model" button, which does the same as `stop`) is **opt-in and for the home network only**: it does not exist unless `VIETPOET_ALLOW_SWITCH=1`,
it accepts requests only from loopback / private (RFC 1918, link-local) addresses, it refuses anything carrying
proxy headers (so it stays disabled behind a reverse proxy or tunnel), and it only ever acts on a vLLM
server at 127.0.0.1. Leave the variable unset for anything reachable from the internet. The model switcher is Linux-only.

### Other servers (llama.cpp and any OpenAI-compatible API)

The 4B and 9B models are also published as GGUF (llama.cpp's format, used by LM Studio) on Hugging Face,
[4B](https://huggingface.co/peterbuitho/VietPoet-Qwen3.5-4B-GGUF) and [9B](https://huggingface.co/peterbuitho/VietPoet-Qwen3.5-9B-GGUF):
`Q8_0` (near-lossless) and `Q4_K_M` (about 60% smaller), converted with llama.cpp's `convert_hf_to_gguf.py` and `llama-quantize`.

| File | Size |
|---|---|
| `VietPoet-Qwen3.5-4B-Q8_0.gguf` / `-Q4_K_M.gguf` | 4.6 GB / 2.8 GB |
| `VietPoet-Qwen3.5-9B-Q8_0.gguf` / `-Q4_K_M.gguf` | 9.8 GB / 5.8 GB |

Quality is unchanged: on 40 prompts the 4B `Q8_0` scored 0.995 (all poems valid) with the line-by-line sampler, against
0.994 for the 16-bit model on the same prompts.

The sampler talks to any OpenAI-compatible server, so the same page works against `llama-server` or LM Studio on any
system: `VIETPOET_BASE_URL=http://localhost:1234/v1 VIETPOET_MODEL=<model name> python -m app.webui`. Servers differ from
vLLM, so the sampler adapts: it reads log-probabilities in either format, learns a server's cap on samples per request
(llama.cpp allows at most as many as it has parallel slots; LM Studio allows one) and splits the request, and falls back to
picking without log-probabilities if a server has none.

Speed for one 8-line poem (16 candidates per line unless noted): vLLM on the RTX 4090 about 2 s; LM Studio on the 4090
about 11 to 14 s with 16 parallel predictions; `llama-server` on the 4090 about 24 s with 16 parallel slots (37 s with 4);
CPU only, 4 cores of a fast desktop chip, `Q4_K_M`, 4 candidates per line: about 15 to 17 s.

## Results

Same 200 held-out prompts (100 topics x 2 phrasings, never used in training), 1 sample each
unless stated. Numbers are means over the 200 poems; "pass rate" = poems with correct length,
score >= 0.95, no repeated lines.

| System | Length | Tone | Rhyme | **Score** | Pass rate |
|---|---|---|---|---|---|
| Qwen3.5-4B, no training | 0.36 | 0.24 | 0.06 | **0.14** | 0% |
| + QLoRA fine-tune (SFT) | 1.00 | 0.92 | 0.74 | **0.82** | 9.5% |
| + generate / validate / repair loop | 1.00 | 0.94 | 0.92 | **0.93** | 39.5% |

- The untrained model ignores the form entirely: it rambles, adds commentary and repeats stanzas.
- Fine-tuning fixed structure almost completely (length 0.36 -> 1.00) in ~21 minutes of training.
- The repair loop mostly helps **rhyme** (0.74 -> 0.92, average 2.6 rounds). Tone barely moves
  (0.92 -> 0.94); line-by-line sampling below fixes that.

**Read this honestly:** these scores measure *form*, not *poetry*. Sample poems are correct
lục-bát but the meaning is often loose (e.g. an 8-line poem about a child missing their mother
drifts into "đón chồng trở về"). Training prompts only had the poem *title* as topic, so
topic-following is weak. Eval loss (3.20 -> 2.87) only shows the model fits the training poems;
it is not a quality score.

### Line-by-line sampling (fixes the tone problem)

The repair loop left one rule badly broken: in a bát line, the 6th and 8th syllables must both be
bằng but one huyền and one ngang. The fine-tuned model broke it in **38%** of bát lines (about 94% of
poems had at least one tone error); the repair loop only got that to 32%. The other tone positions
(2, 4, 6, 8) were already mostly fine (1-5% errors).

Fix ([app/agent.py](app/agent.py) `create_poem_linewise`): write the poem **one line at a time**. For each
line, sample 16 candidates from the model, keep only those the validator accepts given the lines so
far, and pick the most fluent of them (best mean token log-probability minus a penalty for repeating
earlier wording). If nothing passes, sample more, then fall back to the fewest violations.

Compared on the same 100 "8 câu" prompts (mean over poems; "paper" = the paper authors' independent
scorer from `vietnamese-poem-classifier`, which uses a different rule variant and is stricter on
near-rhymes; "valid" = my validator's pass rate):

| System | My score | Tone | Rhyme | Valid | Paper score | Paper tone | distinct-2 | Repeated openings |
|---|---|---|---|---|---|---|---|---|
| Qwen3.5-4B, no training | 0.17 | 0.29 | 0.07 | 0% | 0.43 | 0.58 | 0.94 | 0.14 |
| + fine-tune | 0.81 | 0.92 | 0.73 | 12% | 0.87 | 0.93 | 0.95 | 0.22 |
| + repair loop | 0.94 | 0.94 | 0.93 | 43% | 0.92 | 0.95 | 0.97 | 0.18 |
| line-by-line, 16 candidates, no repetition penalty | 1.00 | 1.00 | 0.99 | 100% | 0.96 | 1.00 | 0.88 | 0.32 |
| **line-by-line, 16 candidates, with repetition penalty** | **0.99** | **1.00** | **0.99** | **98%** | **0.96** | **1.00** | **0.98** | **0.13** |
| line-by-line, 4 candidates (3x faster) | 0.99 | 1.00 | 0.98 | 92% | 0.95 | 1.00 | 0.98 | 0.15 |
| *reference: real poems, validation set* | 0.96 | 0.99 | 0.94 | 62% | 0.94 | 0.98 | 0.98 | 0.17 |

How to read it:
- Tone is fixed and the independent scorer agrees (0.95 -> 1.00), so this isn't my validator grading itself.
- A rerun with identical settings moved the score by about 0.001, so these differences are real, not noise.
- Without the repetition penalty the sampler produced repetitive poems (five lines starting "Mùa thu ..."):
  the penalty removes that at almost no cost in rule scores. Wording variety now matches real poems.
- Cost: about 90 s for 100 poems with 16 candidates per line (8 parallel requests), 35 s with 4.
- **It scores above real poems only because real poems break the rules more often.** This shows the rules
  are met, not that the poems are better; meaning and beauty still need human judgment.
  Poems can still be off-topic or odd ("nhớ mẹ đón chồng").

### Larger models: Qwen3.5-9B and Gemma 4 12B

Same data, same training settings (LoRA r=16, 2 epochs, 8,000 poems), same 100 "8 câu" prompts and same
scoring; only the base model changes (`unsloth/Qwen3.5-9B`, `unsloth/gemma-4-12b-it`).

Raw output, one sample per prompt (no repair, no sampling tricks):

| Model | Score | Tone | Rhyme | Valid | Poems with a tone error | 6th/8th-syllable rule broken |
|---|---|---|---|---|---|---|
| Qwen3.5-4B | 0.812 | 0.920 | 0.728 | 12% | 93% | 38% of bát lines |
| Qwen3.5-9B | 0.829 | 0.941 | 0.746 | 14% | 63% | 10% |
| Gemma 4 12B | 0.844 | 0.950 | 0.767 | 18% | 55% | 3% |

With line-by-line sampling (16 candidates per line, repetition penalty):

| Model | Score | Tone | Rhyme | Valid | Independent score | distinct-2 | Repeated openings |
|---|---|---|---|---|---|---|---|
| Qwen3.5-4B | 0.994 | 1.000 | 0.990 | 98% | 0.956 | 0.98 | 0.13 |
| Qwen3.5-9B | 0.994 | 1.000 | 0.990 | 98% | 0.955 | 0.97 | 0.14 |
| Gemma 4 12B | 0.996 | 1.000 | 0.993 | 100% | 0.960 | 0.99 | 0.13 |

How to read it:
- **A bigger model fixes most of the tone weakness on its own**: the 6th/8th-syllable rule that the 4B broke in
  38% of bát lines drops to 10% (9B) and 3% (Gemma). Rhyme improves only a little, so the raw score moves from
  0.81 to 0.84.
- **With line-by-line sampling the three models are equivalent on the rules** (0.994-0.996). The sampler alone
  removes the tone problem at every size, so extra parameters buy little for *form*. Whether the larger models write
  *better poems* is a question for human judgment, not for these scores.
- The 4B is the cheapest to run: 100 poems in about 1.5 min line by line, versus 2-3.7 min for the others.
- Caveats: Gemma 4 was served in FP8 (its 16-bit weights are 23 GB and do not fit on a 24 GB card), the Qwen
  models in 16-bit; 100 prompts, one run each. Eval loss is not comparable across models (different tokenizers).
- Gemma 4 needs a newer `transformers` than Unsloth Studio ships, so it was trained from a separate environment
  with the same Unsloth/TRL/PEFT versions; its chat template, end token and raw-prompt format differ from Qwen
  (see `--end-token` in `scripts/train_sft.py` and `VIETPOET_FAMILY` in `app/prompts.py`).

### Tests

`pytest` (70 tests, no GPU or server needed; the Gemma tokenizer test is skipped offline):
- validator: every rule, near-rhymes, duplicate lines, odd line counts, syllable parsing, output cleaning;
- sampler: run against a scripted fake model, covering rule-abiding line beats a more probable illegal one,
  fallback to fewest violations, extra rounds, repeated rhyme words, repetition penalty;
- the prompt renderer used for line-by-line generation equals the tokenizer's chat template;
- the home-only guard of the model switcher ([Linux](#linux-vllm)): which addresses and proxy headers are accepted.

The tests were mutation-checked: deliberately breaking the tiếng-4 rule, the 6-vs-8 rule, or the sampler's
selection makes them fail.

Raw outputs: `data/eval/*.jsonl` (local, git-ignored); summary rows: `data/eval/summary.jsonl`.

## What was done, end to end

1. **Environment.** Kubuntu 26.04, RTX4090, shell runs inside a VSCodium, Unsloth and vLLM.
2. **Validator first** ([app/validator.py](app/validator.py)). Pure Python, no LLM. Reports
   errors down to line and syllable ("Câu 3, tiếng thứ 4 'quê' ... cần thanh trắc"), which
   is what the repair prompt needs. I wrote my own instead of using the paper's
   `vietnamese-poem-classifier` package, which needs torch and only gives aggregate scores.
   Rules: câu lục 6 tiếng, câu bát 8; tiếng 2/6 bằng, tiếng 4 trắc, tiếng 8 bằng with a different
   mark from tiếng 6; rhyme 6-6 inside a pair and 8-6 into the next pair. Near-rhymes (vần thông,
   e.g. *phong/hồng*, *đèn/truyền*) count 0.95. Sanity check: the first 8 lines of Truyện Kiều
   score 0.983; a deliberately broken poem scores 0.24 with precise errors.
3. **Dataset** ([scripts/prepare_dataset.py](scripts/prepare_dataset.py)).
   - Source: `phamson02/vietnamese-poetry-corpus` (198,598 poems, CC BY 4.0).
   - Kept genre = lục bát (89,943), then filtered with the validator:

     | Step | Removed |
     |---|---|
     | odd line count, or outside 4-16 lines | 26,186 |
     | wrong syllable counts | 2,006 |
     | repeated lines / non-Vietnamese tokens | 6,299 |
     | validator score < 0.90 (the paper's threshold) | 25,694 |
     | exact duplicates | 84 |
     | **kept** | **29,298** |

   - Sampled 8,000 train + 300 validation poems. The corpus is lowercased with spaced punctuation,
     so lines were detokenized and capitalised.
   - Each poem became a chat example (system / user request / poem) with varied request templates
     built from the poem title and line count ([app/prompts.py](app/prompts.py)).
4. **Held-out test set.** 200 prompts written by hand from 100 topics (traditional and odd ones:
   "lập trình viên thức khuya", "con robot biết nhớ nhà"), never in training
   ([scripts/make_test_prompts.py](scripts/make_test_prompts.py)).
5. **Baseline.** Served the untrained model with vLLM and scored it
   ([scripts/serve.sh](scripts/serve.sh), [scripts/evaluate.py](scripts/evaluate.py)).
   Also proved the whole pipeline (server -> client -> validator) works before training.
6. **Training smoke test.** 5 steps (`--max-steps 5`) to check the prompt format, loss masking
   and saving before spending 20 minutes. Confirmed the rendered prompt matches what vLLM sends
   at inference (thinking disabled).
7. **Training** ([scripts/train_sft.py](scripts/train_sft.py)), headless Unsloth QLoRA.
8. **Merge + serve + evaluate** the fine-tuned model, raw and with the agent loop.
9. **Diagnose and fix tone** with line-by-line sampling, then **repeat with larger models** (Qwen3.5-9B, Gemma 4 12B) for a
   like-for-like comparison.

## Training parameters

Saved automatically per run to `runs/<name>/train_config.json` (with package versions) and
`runs/<name>/log_history.json` (loss curves): [sft-v1](runs/sft-v1), [sft-9b-v1](runs/sft-9b-v1),
[sft-gemma4-12b-v1](runs/sft-gemma4-12b-v1).

| | Qwen3.5-4B | Qwen3.5-9B | Gemma 4 12B |
|---|---|---|---|
| Base model | `unsloth/Qwen3.5-4B` | `unsloth/Qwen3.5-9B` | `unsloth/gemma-4-12b-it` |
| Precision | 4-bit QLoRA | 4-bit QLoRA | 4-bit QLoRA |
| LoRA | r=16, alpha=16, dropout=0, all attention + MLP projections | same | same |
| Trainable parameters | 21.2M (0.47%) | 29.1M (0.31%) | 65.6M (0.55%) |
| Optimiser | AdamW 8-bit, lr 2e-4, linear schedule, warmup 3%, weight decay 0.01 | same | same |
| Batch | 2 x grad-accum 4 = 8; 2 epochs = 2,000 steps; max length 1024 | same | same |
| Loss target | completion only (the poem, not the request) | same | same |
| Time on the 4090 | ~21 min | ~30 min | ~46 min |
| Train loss | 3.84 -> 2.77 | 3.68 -> 2.60 | 5.17 -> 2.41 |
| Eval loss | 3.20 -> 2.87 | 2.98 -> 2.72 | 2.70 -> 2.50 |
| Software | unsloth 2026.9.7, trl 0.23.1, peft 0.18.1, torch 2.11; transformers 5.5.0 | same | same, transformers 5.17.0 |

The eval loss was still falling slowly at the end of every run, with no sign of overfitting.

## Project layout

```
app/          validator.py  prompts.py  agent.py (repair loop + line-by-line)  webui.py  serving.py (model switcher)
scripts/      prepare_dataset.py  make_test_prompts.py  train_sft.py  merge_adapter.py
              serve.sh  switch_model.sh  evaluate.py
packaging/    windows/ (launcher, README for the zip)  huggingface/ (model cards)
tests/        pytest suite
data/         train.jsonl  validation.jsonl  test_prompts.jsonl  eval/
runs/         one folder per training run (config, loss history, log)
models/       LoRA adapters (weights are git-ignored)
```

## Reproduce

```bash
# 1. data
.venv/bin/python scripts/prepare_dataset.py --limit 8000
.venv/bin/python scripts/make_test_prompts.py

# 2. train (Unsloth env python)
export OPENSSL_CONF=/dev/null LD_LIBRARY_PATH=/run/host/usr/lib/x86_64-linux-gnu
~/.unsloth/studio/unsloth_studio/bin/python scripts/train_sft.py --name sft-v1
~/.unsloth/studio/unsloth_studio/bin/python scripts/merge_adapter.py sft-v1

# 2b. other models: same script, different base model
~/.unsloth/studio/unsloth_studio/bin/python scripts/train_sft.py --name sft-9b-v1 --base-model unsloth/Qwen3.5-9B
#     Gemma 4 needs transformers >= 5.17 (newer than Studio's), so use an environment with it, plus its end token:
python scripts/train_sft.py --name sft-gemma4-12b-v1 --base-model unsloth/gemma-4-12b-it --end-token "<turn|>"

# 3. serve + evaluate (stop the server before training: VRAM)
bash scripts/serve.sh ~/vietpoet-models/sft-v1/merged
.venv/bin/python scripts/evaluate.py --model vietpoet --tag sft-v1 --mode raw     # or --mode agent

#    9B: VLLM_GPU_UTIL=0.90 bash scripts/serve.sh <model> --max-num-batched-tokens 1024 --max-num-seqs 32
#    Gemma 4: VIETPOET_FAMILY=gemma VLLM_GPU_UTIL=0.90 bash scripts/serve.sh <model> --quantization fp8 \
#             --max-num-batched-tokens 2560 --max-num-seqs 32 --limit-mm-per-prompt '{"image":0,"audio":0}'

# 3b. line-by-line sampling, and the tests
.venv/bin/python scripts/evaluate.py --model vietpoet --tag sft-v1-lw16 --mode linewise --only-8
.venv/bin/python -m pytest

# 4. web UI (uses line-by-line sampling; needs the server running)
.venv/bin/python -m app.webui
```

## Limits and next steps

- Form scores cannot say whether the larger models write *better* poems; that needs human comparison of
  the three models' line-by-line output.
- Form only: no automatic check of meaning, imagery or naturalness; those need human judgment.
- Topic-following is weak because prompts came from titles; generate richer per-poem summaries
  with an LLM and retrain.
- Line-by-line sampling commits to each line greedily; a beam or backtracking search could help later lines.
  Preference training (DPO) on human choices could then improve meaning, not just form.
- Only lục-bát; three models, one training run each, evaluated on 100 prompts.
