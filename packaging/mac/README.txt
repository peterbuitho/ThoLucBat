VietPoet - a Vietnamese luc-bat poet that runs on your own Mac
==============================================================

A small AI model writes the poem one line at a time; a rule checker makes sure each line has the right
number of syllables, tones and rhyme. Everything runs locally: nothing you type leaves your Mac.

What you need
-------------
* A Mac with Apple silicon (M1 or newer). Intel Macs are not supported.
* LM Studio (free): https://lmstudio.ai  -- install it and open it once (you may close it again; if the launcher
  says LM Studio's service did not start, leave the LM Studio window open).
* An internet connection for the first start (downloads 2.8 to 10 GB, once).
* 16 GB of memory is recommended. The 4B model needs about 5 to 7 GB free while it writes, the 9B model 8 GB or more;
  Macs with 8 GB will struggle.

How to start
------------
1. Unzip this folder anywhere.
2. Open "Start VietPoet.command". The first time macOS may say it cannot check the file: right-click (or
   Control-click) the file, choose "Open", then "Open" again. If that does not work, open Terminal and run:
       xattr -dr com.apple.quarantine "<the unzipped VietPoet folder>"
   then double-click the file again. (This is because the file was downloaded from the internet, not because
   anything is wrong with it.)
3. The first time it asks which model to use, 4B (faster, recommended) or 9B, checks that your Mac has enough
   memory, downloads the model and sets things up (a few minutes). Your choice is saved; later starts take seconds.
4. Your browser opens the poem page. Type a topic, choose the number of lines, press the button.

Close the Terminal window (or press Control+C in it) to stop. That also unloads the model from memory.

To choose again (other model size): open "Change model or hardware.command". Models you already downloaded are
kept, so switching back does not download again.

What to expect
--------------
The launcher looks at your Mac's memory (it is shared by the processor and the graphics) and picks the 8-bit model
(near-lossless) if it fits, otherwise the smaller 4-bit one. Extra memory needed while a poem is being written, measured
with LM Studio on an M2 Pro with 16 GB (the 9B 8-bit figure is an estimate):

  Model  Precision  File     Memory needed  Seconds per poem
  4B     8-bit      4.6 GB   about 6.6 GB   about 20
  4B     4-bit      2.8 GB   about 4.9 GB   about 25
  9B     8-bit      9.8 GB   about 12 GB    (not measured)
  9B     4-bit      5.8 GB   about 7.7 GB   about 36

A poem is 8 lines with 8 candidates per line; other Macs will be faster or slower.

Good to know
------------
* It checks form (line length, tones, rhyme), not meaning. Poems are correct luc-bat but can be odd or
  off-topic. Whether the 9B writes better poems than the 4B is for you to judge.
* The model is downloaded as a GGUF file (the same one the Windows version uses). In LM Studio this ran about five
  times faster and used less memory than the MLX version of the same model (4B 8-bit: 20 seconds against 99 seconds
  per poem), so it is the default. MLX versions exist too: set VIETPOET_FORMAT=mlx to use them.
* The page keeps a private log of poems and your thumbs up/down in the "data" folder next to it.
  Nothing is sent anywhere.
* The page sets the poet's instructions and switches off the model's "thinking" itself, so you do not need to
  change anything in LM Studio. (If you chat with these models directly in LM Studio's own chat window, they
  will not have those settings.)

If something goes wrong
-----------------------
* "LM Studio was not found": install it, open it once, close it, run again.
* Download stopped: run again, it continues where it stopped.
* "LM Studio does not list it": you moved LM Studio's models folder. Run again after setting
  VIETPOET_MODELS_DIR to that folder (Terminal: VIETPOET_MODELS_DIR="/path/to/models" ./launcher/start.sh).
* "Could not load the model": close other big programs, then open "Change model or hardware.command" and
  choose the 4B model.
* "LM Studio's background service did not start": open the LM Studio app, leave it open, run this again.
* Slow: set VIETPOET_CANDIDATES=4 (fewer tries per line: faster, slightly less polished).

Advanced (optional environment variables): VIETPOET_SIZE (4B or 9B), VIETPOET_BITS (8 or 4),
VIETPOET_FORMAT (mlx or gguf), VIETPOET_CANDIDATES, VIETPOET_PORT (page port, default 7860).

Source code and results: https://github.com/peterbuitho/ThoLucBat
Models: https://huggingface.co/peterbuitho (GGUF: VietPoet-Qwen3.5-{4B,9B}-GGUF; MLX: VietPoet-Qwen3.5-4B-MLX-{8bit,4bit})
Training data: phamson02/vietnamese-poetry-corpus (CC BY 4.0). Base models: Qwen3.5-4B and Qwen3.5-9B (Apache-2.0).
