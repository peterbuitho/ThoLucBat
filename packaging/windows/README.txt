VietPoet - a Vietnamese luc-bat poet that runs on your own computer
====================================================================

A small AI model writes the poem one line at a time; a rule checker makes sure each line has the right
number of syllables, tones and rhyme. Everything runs locally: nothing you type leaves your computer.

What you need
-------------
* Windows 10 or 11.
* LM Studio (free): https://lmstudio.ai  -- install it and open it once, then you can close it.
  Use a recent version (the launcher turns off a LM Studio feature that slowed things down and could crash it).
* An internet connection for the first start (downloads 3 to 10 GB, once).
* A graphics card helps a lot. Without one it still works, but each poem takes 15 to 30 seconds or more.

How to start
------------
1. Unzip this folder anywhere (not inside "Program Files").
2. Double-click "Start VietPoet.bat".
3. The first time it asks two questions, then downloads the model and sets things up (a few minutes):
   * Which model: 4B (faster, smaller, recommended) or 9B (larger, needs more memory).
   * Where it runs: on the graphics card (fast) or on the CPU (slow, works anywhere).
   It checks how much free graphics memory you have. If the model you choose does not fit, it offers a smaller
   setup or the CPU. Your choice is saved; later starts take seconds.
4. Your browser opens the poem page. Type a topic, choose the number of lines, press the button.

Close the black window (or press Ctrl+C in it) to stop. That also unloads the model from memory.

To choose again (other model size, graphics card or CPU): double-click "Change model or hardware.bat".
Models you already downloaded are kept, so switching back does not download again.

What to expect
--------------
Roughly how much graphics memory it needs, and what you get (NVIDIA cards; measured on an RTX 4090):

  Model  File used   Graphics memory   Seconds per poem
  4B     Q8_0        about 5 to 6 GB   5 to 14
  4B     Q4_K_M      about 3 to 4 GB   5 to 12
  9B     Q8_0        about 9 to 10 GB  6 to 12
  9B     Q4_K_M      about 5.5 to 7 GB 5 to 12
  CPU    4B / 9B     none              about 15 / 25 (a fast desktop; slower computers take longer)

The launcher picks the best file and speed that fit your free graphics memory. AMD and Intel cards cannot be
measured: you can still try the graphics card (smallest setup) or use the CPU.

Good to know
------------
* It checks form (line length, tones, rhyme), not meaning. Poems are correct luc-bat but can be odd or
  off-topic. In the author's tests the 9B is not better than the 4B on the rules; whether it writes better
  poems is for you to judge.
* The page keeps a private log of poems and your thumbs up/down in the "data" folder next to it.
  Nothing is sent anywhere.
* The page sets the poet's instructions and switches off the model's "thinking" itself, so you do not need to
  change anything in LM Studio. (If you chat with these models directly in LM Studio's own chat window, they
  will not have those settings.)

If something goes wrong
-----------------------
* "LM Studio was not found": install it, open it once, close it, run again.
* Download stopped: run again, it continues where it stopped.
* "Could not load the model": close other programs that use the graphics card, then double-click
  "Change model or hardware.bat" and choose the 4B model or the CPU.
* Slow: choose the 4B model, or set VIETPOET_CANDIDATES=4 (fewer tries per line: faster, slightly less polished).
* If LM Studio itself was open and using the graphics card, close its own chat models first.

Advanced (optional environment variables): VIETPOET_SIZE (4B or 9B), VIETPOET_DEVICE (gpu or cpu),
VIETPOET_QUANT (Q8_0 or Q4_K_M), VIETPOET_CANDIDATES, VIETPOET_PORT (page port, default 7860).

Source code and results: https://github.com/peterbuitho/ThoLucBat
Models: https://huggingface.co/peterbuitho/VietPoet-Qwen3.5-4B-GGUF and .../VietPoet-Qwen3.5-9B-GGUF
Training data: phamson02/vietnamese-poetry-corpus (CC BY 4.0). Base models: Qwen3.5-4B and Qwen3.5-9B (Apache-2.0).
