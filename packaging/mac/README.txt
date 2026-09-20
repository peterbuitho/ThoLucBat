VietPoet - a Vietnamese luc-bat poet that runs on your own Mac
==============================================================

A small AI model writes the poem one line at a time; a rule checker makes sure each line has the right
number of syllables, tones and rhyme. Everything runs locally: nothing you type leaves your Mac.

What you need
-------------
* A Mac with Apple silicon (M1 or newer). Intel Macs are not supported.
* LM Studio (free): https://lmstudio.ai  -- install it and open it once, then you can close it.
* An internet connection for the first start (downloads 2.5 to 10 GB, once).
* 8 GB of memory is enough for the 4B model; the 9B model wants 16 GB or more.

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
The launcher looks at your Mac's memory (it is shared by the processor and the graphics) and picks the 8-bit
model (near-lossless) if it fits, otherwise the smaller 4-bit one. Rough memory needs (estimates, not yet measured
on a Mac):

  Model  Precision   Memory needed
  4B     8-bit       about 6 GB
  4B     4-bit       about 3.5 GB
  9B     8-bit       about 11 GB
  9B     4-bit       about 6.5 GB

Good to know
------------
* It checks form (line length, tones, rhyme), not meaning. Poems are correct luc-bat but can be odd or
  off-topic. Whether the 9B writes better poems than the 4B is for you to judge.
* The model is downloaded in Apple's MLX format. If that is not available it uses the GGUF file (the same one
  the Windows version uses), which also runs well on Apple silicon.
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
* Slow: set VIETPOET_CANDIDATES=4 (fewer tries per line: faster, slightly less polished).

Advanced (optional environment variables): VIETPOET_SIZE (4B or 9B), VIETPOET_BITS (8 or 4),
VIETPOET_FORMAT (mlx or gguf), VIETPOET_CANDIDATES, VIETPOET_PORT (page port, default 7860).

Source code and results: https://github.com/peterbuitho/ThoLucBat
Models: https://huggingface.co/peterbuitho (the MLX versions, VietPoet-Qwen3.5-{4B,9B}-MLX-{8bit,4bit}, and the GGUF versions)
Training data: phamson02/vietnamese-poetry-corpus (CC BY 4.0). Base models: Qwen3.5-4B and Qwen3.5-9B (Apache-2.0).
