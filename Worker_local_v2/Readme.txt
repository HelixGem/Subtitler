============================================================
  Subtitler Local v2.0.0
  Self-hosted WhisperX transcription server
  For use with Subtitler plugin in Adobe After Effects
============================================================

OVERVIEW
--------
Subtitler Local runs entirely on your machine.
No internet connection required after setup.
No usage limits. No API keys.

Transcription is powered by WhisperX (faster-whisper backend)
with word-level alignment for precise subtitle timing.
Translation is powered by Argos Translate (offline).


SYSTEM REQUIREMENTS
-------------------
All platforms:
  - Python 3.9 or newer
  - ffmpeg
  - 4 GB RAM minimum (8 GB recommended)
  - Internet connection for initial setup (model downloads)

Windows / Linux (recommended):
  - NVIDIA GPU with CUDA support
  - NVIDIA drivers installed
    NVIDIA driver 560.x or newer (for CUDA 12.6 support)
    Check: nvidia-smi → Driver Version column
  - 4 GB VRAM minimum (6+ GB for large models)

macOS:
  - Apple Silicon (M1/M2/M3/M4) — MPS acceleration
  - Intel Mac — CPU only (slower, but functional)

CPU fallback:
  - Any platform without a supported GPU
  - Works but significantly slower than GPU


WHISPER MODELS
--------------
Model           Size        Speed       Accuracy
----------------------------------------------------
tiny            ~75 MB      fastest     basic
base            ~150 MB     very fast   good
small           ~500 MB     fast        better
medium          ~1.5 GB     moderate    great
large-v2        ~3 GB       slow        excellent
large-v3        ~3 GB       slow        excellent
large-v3-turbo  ~1.6 GB     moderate    excellent

Recommendation:
  - Quick results   : small
  - Best accuracy   : large-v3
  - Best balance    : large-v3-turbo

Models are downloaded automatically on first use
or during setup wizard.


WORD-LEVEL ALIGNMENT
--------------------
WhisperX improves subtitle timing using language-specific
alignment models (wav2vec2 and similar).

Supported languages:
  ar ca cs da de el en es fa fi fr
  he hi hu it ja ko ml nl pl pt ru
  te tr uk ur vi zh

For unsupported languages:
  Transcription works normally.
  Segment-level timestamps are used (still accurate).
  Alignment is skipped automatically — no errors.

Alignment models are downloaded automatically
on first use for each language.


INSTALLATION
------------

IMPORTANT — NVIDIA drivers:
  torch 2.8.x requires CUDA 12.6 or newer.
  Check your driver version: nvidia-smi
  Required: Driver 560.x or newer.

  If your driver is older:
    Update at: https://www.nvidia.com/drivers

Windows:
  1. Double-click Subtitler_Local.bat
     Setup wizard runs automatically if needed.

  OR manually:
  1. Open Command Prompt in this folder
  2. Run: python subtitler_local.py --setup

macOS / Linux:
  1. Install ffmpeg first:
       macOS : brew install ffmpeg
       Ubuntu: sudo apt install ffmpeg
       Fedora: sudo dnf install ffmpeg
       Arch  : sudo pacman -S ffmpeg

  2. Make script executable (once):
       chmod +x subtitler_local.sh

  3. Run:
       bash subtitler_local.sh
     Setup wizard runs automatically if needed.

  OR manually:
       python3 subtitler_local.py --setup


STARTING THE SERVER
-------------------

Windows:
  Double-click Subtitler_Local.bat
  OR: python subtitler_local.py

macOS / Linux:
  bash subtitler_local.sh
  OR: python3 subtitler_local.py

With options:
  python subtitler_local.py --model large-v3
  python subtitler_local.py --model medium --port 9000


SETUP WIZARD WALKTHROUGH
------------------------

Run the setup wizard:
  Windows:        Subtitler_Local.bat --setup
                  OR: python subtitler_local.py --setup
  macOS / Linux:  bash subtitler_local.sh --setup
                  OR: python3 subtitler_local.py --setup

The wizard runs 5 steps. Below is a full walkthrough
with expected prompts and recommended answers.

------------------------------------------------------------
STEP 1 of 5 — System requirements
------------------------------------------------------------

The wizard checks Python, GPU, ffmpeg and pip automatically.
No input required for most checks.

You may see:

  [Windows only] ffmpeg not found:
  > Download ffmpeg automatically? [Y/n]:
    Y — downloads ffmpeg.exe and ffprobe.exe automatically
        to the tools\ subfolder next to subtitler_local.py
        (~140 MB, source: github.com/BtbN/FFmpeg-Builds)
    n — wizard prints manual install instructions and exits.
        Download from https://ffmpeg.org/download.html,
        place ffmpeg.exe and ffprobe.exe in tools\ folder,
        then re-run setup.

  [macOS] ffmpeg not found:
    Wizard prints instructions and exits. Install manually:
    brew install ffmpeg
    Then re-run setup.

  [Linux] ffmpeg not found:
    Wizard prints instructions and exits. Install manually:
    sudo apt install ffmpeg   (Ubuntu/Debian)
    sudo dnf install ffmpeg   (Fedora)
    Then re-run setup.

  No GPU detected:
  > Continue? [Y/n]:
    Y — continues in CPU mode (slower but functional).
        Note: if you have an NVIDIA GPU this warning may appear
        before PyTorch is installed. Answer Y and continue —
        your GPU will be detected automatically in Step 2.
    n — exits setup.

------------------------------------------------------------
STEP 2 of 5 — Python packages
------------------------------------------------------------

The wizard checks and installs required Python packages.
Each package prompts for confirmation before installing.

  PyTorch (if not installed):
  > Install PyTorch with CUDA support? (~3 GB) [Y/n]:
    Y — downloads PyTorch with CUDA 12.6 support (~2.5 GB).
        This may take several minutes depending on
        your internet connection. GPU (CUDA or MPS) will be
        confirmed automatically after installation.
    n — exits setup. PyTorch is required.

    Note: after PyTorch installs the wizard confirms
    your GPU automatically:
      2026-04-11 [INFO] Device confirmed: CUDA — RTX 3060 (12.0 GB VRAM)

  whisperx + faster-whisper (if not installed):
  > Install whisperx + faster-whisper? [Y/n]:
    Y — installs whisperx, faster-whisper, ctranslate2.
    n — exits setup. whisperx is required.

  argostranslate (if not installed):
  > Install argostranslate (offline translation)? [Y/n]:
    Y — installs offline translation engine (~50 MB).
        Required only if you need subtitle translation.
    n — skips. Server works without it.
        Translation will be unavailable.
        Install later: pip install argostranslate

  FastAPI + uvicorn (if not installed):
  > Install FastAPI + uvicorn (web server)? [Y/n]:
    Y — installs FastAPI, uvicorn, python-multipart.
    n — exits setup. FastAPI is required.

------------------------------------------------------------
STEP 3 of 5 — Whisper models
------------------------------------------------------------

The wizard shows available models and their download sizes:

  Model            Size          Status
  ----------------------------------------
  tiny             ~75 MB        not downloaded
  base             ~150 MB       not downloaded
  small            ~500 MB       not downloaded
  medium           ~1.5 GB       not downloaded
  large-v2         ~3 GB         not downloaded
  large-v3         ~3 GB         not downloaded
  large-v3-turbo   ~1.6 GB       not downloaded

  If no models are installed:
  > No models found. Download 'tiny' (~75 MB)? [Y/n]:

    Y — downloads tiny model. Recommended for first run
        to verify everything works before downloading
        larger models.
    n — skips tiny. You will be prompted to choose
        another model in the next prompt below.

  IMPORTANT — if you want a specific model instead of tiny:
    Answer n to the tiny prompt, then type the model
    name when the next prompt appears:

    > Download a model? (enter name or press Enter to skip):
      Type: large-v3-turbo    (press Enter to confirm)

    The chosen model downloads immediately.
    You can download multiple models one after another.
    Press Enter without typing a name to move to Step 4.

  Examples:
    Want only large-v3-turbo:
      tiny prompt     → n
      next prompt     → large-v3-turbo  → Enter
      next prompt     → Enter  (done)

    Want small now, large-v3-turbo later:
      tiny prompt     → n
      next prompt     → small  → Enter
      next prompt     → large-v3-turbo  → Enter
      next prompt     → Enter  (done)

    Want tiny for testing + large-v3-turbo for production:
      tiny prompt     → Y
      next prompt     → large-v3-turbo  → Enter
      next prompt     → Enter  (done)

  Models are stored in HuggingFace cache:
    Windows : C:\Users\<user>\.cache\huggingface\hub\
    macOS   : /Users/<user>/.cache/huggingface/hub/
    Linux   : /home/<user>/.cache/huggingface/hub/

  Models are shared between sessions and are not
  re-downloaded if already present.

  You can download additional models later:
    python subtitler_local.py --setup
    (wizard skips already installed packages,
     goes directly to model selection)

  Or start server with a specific model
  (downloads automatically if not present):
    python subtitler_local.py --model large-v3-turbo

------------------------------------------------------------
STEP 4 of 5 — Translation languages
------------------------------------------------------------

  Skipped automatically if argostranslate was not installed.

  > Install a language?
    (e.g. 'ru', 'es', 'de' — or press Enter to skip):

    Type a language code to install translation for that
    language (both directions: en→lang and lang→en).
    Press Enter to skip and move to Step 5.

  Examples:
    ru  — Russian
    es  — Spanish
    de  — German
    fr  — French
    ja  — Japanese
    zh  — Chinese
    ko  — Korean

  The prompt repeats so you can install multiple languages.
  Press Enter on an empty prompt to finish.

  Install translation languages later:
    python subtitler_local.py --install-lang ru

  Note: translation uses English as a pivot language.
  Example: Japanese → Russian works automatically as
  ja → en → ru without installing a direct ja→ru pair.

------------------------------------------------------------
STEP 5 of 5 — Summary
------------------------------------------------------------

  Setup prints a summary of everything installed:

  Device:           CUDA — NVIDIA GeForce RTX 3060 (12.0 GB VRAM)
  ffmpeg:           D:\...\tools\ffmpeg.exe
  Whisper models:   large-v3-turbo
  Alignment models: none cached (auto-download on first use)
  Translation:      en→ru, ru→en

  Start the server:
    python subtitler_local.py
    python subtitler_local.py --model large-v3-turbo
    Subtitler_Local.bat

  After Effects plugin settings:
    Server URL : http://localhost:8765
    Mode       : Direct
    API Key    : local

------------------------------------------------------------
NOTES
------------------------------------------------------------

Re-running setup is safe:
  The wizard detects already installed packages and skips
  them. Only missing components are installed.
  Use this to add new models or languages at any time:
    python subtitler_local.py --setup

Alignment models (word-level timestamps):
  Not shown during setup. Downloaded automatically on first
  transcription request for each language detected.
  No action required from the user.

First transcription after setup:
  May take longer than usual — the alignment model for
  the detected language is downloaded at this point.
  Subsequent runs use the cached model instantly.


AFTER EFFECTS PLUGIN SETTINGS
------------------------------
After starting the server, open the Subtitler plugin
in After Effects and set:

  Server URL : http://localhost:8765
  Mode       : Direct
  API Key    : local

If you changed the port:
  Server URL : http://localhost:YOUR_PORT


SUBTITLE FORMATS
----------------
standard  6 words per line, 2 lines max  (default)
short     3 words per line, 1 line
word      1 word per subtitle (karaoke style)

All formats benefit from word-level alignment
when the language is supported.


TRANSLATION
-----------
Offline translation via Argos Translate.
Translation is optional — skip during setup if not needed.

Install a language pair:
  python subtitler_local.py --install-lang ru
  python subtitler_local.py --install-lang es
  python subtitler_local.py --install-lang de

List installed languages:
  python subtitler_local.py --list-langs

Translation uses English as a pivot language when
no direct translation pair is available.

Example: Japanese → Russian
  ja → en → ru (automatic, no extra steps needed)


COMMAND LINE REFERENCE
-----------------------
python subtitler_local.py                    Start server (default settings)
python subtitler_local.py --setup            Run setup wizard
python subtitler_local.py --check            Check installation status
python subtitler_local.py --model medium     Use specific model
python subtitler_local.py --port 9000        Use custom port
python subtitler_local.py --list-models      Show available models
python subtitler_local.py --install-lang ru  Install Russian translation
python subtitler_local.py --list-langs       List translation languages


FILE STRUCTURE
--------------
subtitler_local.py      Main server script
Subtitler_Local.bat     Windows launcher
subtitler_local.sh      macOS / Linux launcher
README.txt              This file

logs/
  subtitler_local.log   Server log file

temp_local/
  (temporary files during processing, auto-cleaned)

tools/
  ffmpeg.exe            ffmpeg binary (Windows, auto-installed)
  ffprobe.exe           ffprobe binary (Windows, auto-installed)

Model cache (managed automatically):
  Windows : C:\Users\<user>\.cache\huggingface\hub\
  macOS   : /Users/<user>/.cache/huggingface/hub/
  Linux   : /home/<user>/.cache/huggingface/hub/


TROUBLESHOOTING
---------------

"PyTorch installation failed" on Windows/Linux:
  torch 2.8.x is only available for CUDA 12.6+.
  Your driver may be too old.

  Check driver version:
    nvidia-smi

  If Driver Version < 560.x:
    Update NVIDIA drivers: https://www.nvidia.com/drivers
    Then re-run setup: python subtitler_local.py --setup

  If you cannot update drivers:
    Install manually with CUDA 12.4:
      pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 ^
          --index-url https://download.pytorch.org/whl/cu124
    Then install older whisperx:
      pip install whisperx==3.1.5

"GPU not detected during setup (Step 1)":
  This is expected if PyTorch is not yet installed.
  The wizard will detect your GPU automatically
  after PyTorch installation in Step 2.
  Continue setup and answer Y when prompted.

"CUDA not available" on Windows/Linux:
  Reinstall PyTorch with CUDA support:
    python -m pip install torch torchvision torchaudio \
      --index-url https://download.pytorch.org/whl/cu121

"MPS not available" on Apple Silicon:
  Update macOS to 12.3 or newer.
  Update PyTorch:
    pip install torch --upgrade

"Model download failed: cannot import name
 'mark_subclass_constructor_exportable_experimental'":

  PyTorch version installed on your system is too new
  and incompatible with the current whisperx version.

  Fix:
    pip uninstall torch torchvision torchaudio -y
    pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 ^
        --index-url https://download.pytorch.org/whl/cu126

  Then re-run setup:
    python subtitler_local.py --setup

  Check your versions:
    pip show torch whisperx faster-whisper

"whisperx not found":
  python -m pip install whisperx

"ffmpeg not found" on macOS:
  brew install ffmpeg

"ffmpeg not found" on Linux:
  sudo apt install ffmpeg

"No alignment model for language X":
  Not an error. Transcription continues with
  segment-level timestamps automatically.

"Out of memory" (GPU):
  Use a smaller model:
    python subtitler_local.py --model small
  Or:
    python subtitler_local.py --model base

Translation not working:
  Install the language pair:
    python subtitler_local.py --install-lang <code>
  Check installed pairs:
    python subtitler_local.py --list-langs

Server not reachable from After Effects:
  1. Check server is running (console window open)
  2. Check port matches plugin settings (default: 8765)
  3. Check firewall is not blocking port 8765
  4. Try: http://127.0.0.1:8765 instead of localhost


PERFORMANCE TIPS
----------------
- Use large-v3-turbo for best speed/accuracy balance
- Keep temp_local/ folder on an SSD
- Close other GPU-intensive applications during transcription
- For batch work leave server running between sessions
  (model stays loaded in memory)


UPDATING
--------
To update Subtitler Local:
  1. Replace subtitler_local.py with the new version
  2. Run: python subtitler_local.py --setup
     (only installs what is missing or outdated)


LICENSES
--------
Subtitler Local uses the following open-source components:

  WhisperX          MIT License
  faster-whisper    MIT License
  OpenAI Whisper    MIT License
  Argos Translate   MIT License
  FastAPI           MIT License
  PyTorch           BSD License
  ffmpeg            LGPL / GPL

============================================================
  Subtitler Local v2.0.0
  https://subtitler.online
============================================================