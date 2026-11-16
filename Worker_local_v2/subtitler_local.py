#!/usr/bin/env python3
"""
Subtitler Local — Self-hosted transcription & translation server.
Mimics subtitler.online API for After Effects plugin compatibility.

Usage:
    First run (setup):   python subtitler_local.py --setup
    Start server:        python subtitler_local.py
    Custom port:         python subtitler_local.py --port 9000
    Custom model:        python subtitler_local.py --model medium
    List models:         python subtitler_local.py --list-models
    Install language:    python subtitler_local.py --install-lang ru
    List languages:      python subtitler_local.py --list-langs

Requires: Python 3.9+
    Windows/Linux: NVIDIA GPU with CUDA (recommended)
    macOS:         Apple Silicon MPS (recommended)
    Fallback:      CPU (slow)

ffmpeg is auto-installed if missing (Windows).
On macOS/Linux install via: brew install ffmpeg / apt install ffmpeg
"""

import os
import sys
import platform
import json
import time
import uuid
import shutil
import argparse
import subprocess
import threading
import logging
import zipfile
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

# ============================================================================
# @block LOCAL:INIT:001 @desc Constants & Paths
# ============================================================================

SCRIPT_VERSION  = "2.0.1"
SCRIPT_DIR      = Path(__file__).parent.resolve()
DEFAULT_PORT    = 8765
DEFAULT_MODEL   = "large-v3-turbo"
TEMP_DIR        = SCRIPT_DIR / "temp_local"
LOG_DIR         = SCRIPT_DIR / "logs"
TOOLS_DIR       = SCRIPT_DIR / "tools"

# Platform detection
PLATFORM        = platform.system()          # "Windows" / "Darwin" / "Linux"
IS_WINDOWS      = PLATFORM == "Windows"
IS_MACOS        = PLATFORM == "Darwin"
IS_LINUX        = PLATFORM == "Linux"
IS_APPLE_SILICON = IS_MACOS and platform.machine() == "arm64"

# Whisper models (faster-whisper compatible names)
WHISPER_MODELS = [
    "tiny",
    "base",
    "small",
    "medium",
    "large-v2",
    "large-v3",
    "large-v3-turbo",
]

WHISPER_MODEL_SIZES = {
    "tiny":           "~75 MB",
    "base":           "~150 MB",
    "small":          "~500 MB",
    "medium":         "~1.5 GB",
    "large-v2":       "~3 GB",
    "large-v3":       "~3 GB",
    "large-v3-turbo": "~1.6 GB",
}

# Subtitle format settings
FORMAT_SETTINGS = {
    "standard": {"max_words_per_line": 6, "max_line_count": 2},
    "short":    {"max_words_per_line": 3, "max_line_count": 1},
    "word":     {"max_words_per_line": 1, "max_line_count": 1},
}

# WhisperX: languages WITH native alignment model support
# For all others — alignment is skipped gracefully
WHISPERX_ALIGNMENT_LANGUAGES = {
    "en", "fr", "de", "es", "it", "ja", "zh", "nl", "uk", "pt",
    "ar", "cs", "ru", "pl", "hu", "fi", "fa", "el", "tr", "da",
    "he", "vi", "ko", "ur", "te", "hi", "ca", "ml",
}

# Model cache paths
# faster-whisper stores models in HuggingFace cache
WHISPERX_CACHE_DIR  = Path.home() / ".cache" / "huggingface" / "hub"
# Alignment models also go to HuggingFace cache (wav2vec2 etc.)
ALIGNMENT_CACHE_DIR = Path.home() / ".cache" / "huggingface" / "hub"

# ffmpeg download (Windows only — on macOS/Linux use package manager)
FFMPEG_DOWNLOAD_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip"
)

# ============================================================================
# @block LOCAL:INIT:002 @desc Runtime state
# ============================================================================

# In-memory task storage
tasks      = {}
tasks_lock = threading.Lock()

# ffmpeg/ffprobe resolved paths (updated by find_ffmpeg)
FFMPEG_PATH  = "ffmpeg"
FFPROBE_PATH = "ffprobe"

# ============================================================================
# @block LOCAL:INIT:003 @desc Directory bootstrap
# ============================================================================

TEMP_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
TOOLS_DIR.mkdir(exist_ok=True)

# Prepend tools/ to PATH so bundled ffmpeg is found first
os.environ["PATH"] = str(TOOLS_DIR) + os.pathsep + os.environ.get("PATH", "")

# ============================================================================
# @block LOCAL:INIT:004 @desc Logging
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            LOG_DIR / "subtitler_local.log",
            encoding="utf-8"
        ),
    ],
)
log = logging.getLogger("subtitler_local")

# ============================================================================
# @block LOCAL:INIT:005 @desc Device detection
# ============================================================================

def detect_device() -> str:
    """
    Detect best available compute device.

    Priority:
        1. CUDA  — NVIDIA GPU (Windows / Linux)
        2. MPS   — Apple Silicon (macOS arm64)
        3. CPU   — universal fallback

    Returns:
        "cuda" | "mps" | "cpu"
    """
    # --- CUDA ---
    try:
        import torch
        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            log.info(f"Device: CUDA — {device_name}")
            return "cuda"
    except ImportError:
        pass

    # --- MPS (Apple Silicon) ---
    if IS_APPLE_SILICON:
        try:
            import torch
            if torch.backends.mps.is_available():
                log.info("Device: MPS (Apple Silicon)")
                return "mps"
        except (ImportError, AttributeError):
            pass

    # --- CPU fallback ---
    log.warning("Device: CPU (no GPU acceleration found — processing will be slow)")
    return "cpu"


def device_display_name(device: str) -> str:
    """Human-readable device description for logs and UI."""
    if device == "cuda":
        try:
            import torch
            name = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            vram  = getattr(props, "total_memory", 0) / (1024 ** 3)
            return f"CUDA — {name} ({vram:.1f} GB VRAM)"
        except Exception:
            return "CUDA"
    if device == "mps":
        return "MPS (Apple Silicon)"
    return "CPU"

    # ============================================================================
# @block LOCAL:TOOLS:001 @desc ffmpeg discovery
# ============================================================================

def find_ffmpeg() -> bool:
    """
    Locate ffmpeg and ffprobe binaries.

    Search order:
        1. tools/ directory (bundled, Windows)
        2. Subdirectories of tools/ (extracted zip layout)
        3. System PATH (all platforms)

    Updates globals FFMPEG_PATH and FFPROBE_PATH on success.
    Returns True if both binaries are found.
    """
    global FFMPEG_PATH, FFPROBE_PATH

    # Binary names differ by platform
    bin_name   = "ffmpeg.exe"   if IS_WINDOWS else "ffmpeg"
    probe_name = "ffprobe.exe"  if IS_WINDOWS else "ffprobe"

    # --- 1. tools/ flat layout ---
    candidate_ff = TOOLS_DIR / bin_name
    candidate_fp = TOOLS_DIR / probe_name
    if candidate_ff.exists() and candidate_fp.exists():
        FFMPEG_PATH  = str(candidate_ff)
        FFPROBE_PATH = str(candidate_fp)
        _prepend_path(str(TOOLS_DIR))
        return True

    # --- 2. tools/<subdir>/bin/ layout (Windows zip extraction) ---
    try:
        for subdir in TOOLS_DIR.iterdir():
            if not subdir.is_dir():
                continue
            bin_dir = subdir / "bin"
            if (bin_dir / bin_name).exists() and (bin_dir / probe_name).exists():
                FFMPEG_PATH  = str(bin_dir / bin_name)
                FFPROBE_PATH = str(bin_dir / probe_name)
                _prepend_path(str(bin_dir))
                return True
    except PermissionError:
        pass

    # --- 3. System PATH ---
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        FFMPEG_PATH  = "ffmpeg"
        FFPROBE_PATH = "ffprobe"
        return True

    return False


def _prepend_path(directory: str) -> None:
    """Prepend directory to PATH for current process (avoid duplicates)."""
    current = os.environ.get("PATH", "")
    if directory not in current.split(os.pathsep):
        os.environ["PATH"] = directory + os.pathsep + current


# ============================================================================
# @block LOCAL:TOOLS:002 @desc ffmpeg verification
# ============================================================================

def check_ffmpeg() -> bool:
    """
    Verify ffmpeg is available and executable.
    Returns True on success.
    """
    if not find_ffmpeg():
        log.warning("ffmpeg not found")
        return False

    try:
        result = subprocess.run(
            [FFMPEG_PATH, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            version_line = result.stdout.split("\n")[0]
            log.info(f"ffmpeg: {version_line} ✓")
            if FFMPEG_PATH not in ("ffmpeg", "ffmpeg.exe"):
                log.info(f"  Location: {FFMPEG_PATH}")
            return True
    except FileNotFoundError:
        log.warning("ffmpeg binary not executable")
    except subprocess.TimeoutExpired:
        log.warning("ffmpeg version check timed out")
    except Exception as e:
        log.warning(f"ffmpeg check error: {e}")

    return False


# ============================================================================
# @block LOCAL:TOOLS:003 @desc ffmpeg installation (Windows auto-download)
# ============================================================================

def _download_progress(block_num: int, block_size: int, total_size: int) -> None:
    """Progress callback for urllib.request.urlretrieve."""
    downloaded = block_num * block_size
    if total_size > 0:
        percent  = min(100, downloaded * 100 // total_size)
        mb_done  = downloaded   / (1024 * 1024)
        mb_total = total_size   / (1024 * 1024)
        print(
            f"\r  Downloading: {mb_done:.1f} / {mb_total:.1f} MB ({percent}%)",
            end="", flush=True,
        )
    else:
        mb_done = downloaded / (1024 * 1024)
        print(f"\r  Downloading: {mb_done:.1f} MB", end="", flush=True)


def install_ffmpeg() -> bool:
    """
    Install ffmpeg:
        Windows  — download zip from GitHub, extract to tools/
        macOS    — guide user to: brew install ffmpeg
        Linux    — guide user to: apt/dnf/pacman install ffmpeg
    Returns True if ffmpeg becomes available after the call.
    """

    # ------------------------------------------------------------------ macOS
    if IS_MACOS:
        print("\n  ffmpeg is required. Install via Homebrew:")
        print("    brew install ffmpeg")
        print("\n  No Homebrew? https://brew.sh")
        print("  After installation re-run setup.")
        return False

    # ------------------------------------------------------------------ Linux
    if IS_LINUX:
        print("\n  ffmpeg is required. Install via your package manager:")
        print("    Ubuntu/Debian:  sudo apt install ffmpeg")
        print("    Fedora:         sudo dnf install ffmpeg")
        print("    Arch:           sudo pacman -S ffmpeg")
        print("\n  After installation re-run setup.")
        return False

    # ---------------------------------------------------------------- Windows
    print("\n  ffmpeg is required for audio/video processing.")
    print(f"  It will be downloaded to: {TOOLS_DIR}")
    print(f"  Source: {FFMPEG_DOWNLOAD_URL}")

    answer = input("\n  Download ffmpeg automatically? [Y/n]: ").strip().lower()
    if answer not in ("", "y", "yes"):
        print("\n  Manual installation:")
        print("    1. Download from https://ffmpeg.org/download.html")
        print("    2. Extract ffmpeg.exe and ffprobe.exe")
        print(f"    3. Place them in: {TOOLS_DIR}")
        print("    OR add ffmpeg to system PATH")
        return False

    zip_path = TOOLS_DIR / "ffmpeg.zip"

    try:
        print()
        urllib.request.urlretrieve(
            FFMPEG_DOWNLOAD_URL, str(zip_path), _download_progress
        )
        print("\n  Download complete. Extracting...")

        with zipfile.ZipFile(zip_path, "r") as zf:
            bin_files = [
                f for f in zf.namelist()
                if f.endswith(("/ffmpeg.exe", "/ffprobe.exe"))
            ]

            if not bin_files:
                log.error("ffmpeg.exe not found inside archive")
                return False

            for file_path in bin_files:
                filename = Path(file_path).name
                target   = TOOLS_DIR / filename
                with zf.open(file_path) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                log.info(f"  Extracted: {filename}")

        zip_path.unlink(missing_ok=True)

        if find_ffmpeg():
            log.info("ffmpeg installed successfully ✓")
            return True

        log.error("ffmpeg installation verification failed")
        return False

    except urllib.error.URLError as e:
        log.error(f"Download failed: {e}")
        print("\n  Check your internet connection.")
        print("  Or download manually from https://ffmpeg.org/download.html")
        return False

    except zipfile.BadZipFile:
        log.error("Downloaded file is corrupted")
        zip_path.unlink(missing_ok=True)
        return False

    except Exception as e:
        log.error(f"ffmpeg installation error: {e}")
        return False


# ============================================================================
# @block LOCAL:TOOLS:004 @desc System PATH helpers (setup use)
# ============================================================================

def fix_scripts_path() -> None:
    """
    Add Python Scripts/ directory to PATH for the current process session.
    Ensures pip-installed console scripts (uvicorn etc.) are findable
    immediately after installation without restarting the shell.
    """
    candidates = [
        Path(sys.executable).parent / "Scripts",   # Windows venv / system
        Path(sys.prefix) / "Scripts",              # Windows alt
        Path(sys.executable).parent,               # macOS / Linux
        Path(sys.prefix) / "bin",                  # macOS / Linux venv
    ]
    for scripts_dir in candidates:
        if scripts_dir.exists():
            _prepend_path(str(scripts_dir))

# ============================================================================
# @block LOCAL:SETUP:001 @desc System requirement checks
# ============================================================================

def check_python_version() -> bool:
    """Check Python >= 3.9"""
    if sys.version_info < (3, 9):
        log.error(f"Python 3.9+ required. Current: {sys.version}")
        return False
    log.info(
        f"Python {sys.version_info.major}."
        f"{sys.version_info.minor}."
        f"{sys.version_info.micro} ✓"
    )
    return True


def check_cuda() -> bool:
    """
    Check NVIDIA GPU via nvidia-smi.
    Only relevant on Windows / Linux.
    Returns True if NVIDIA GPU detected.
    """
    if IS_MACOS:
        # CUDA not available on macOS — not an error
        return False

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            gpu_info = result.stdout.strip()
            log.info(f"NVIDIA GPU: {gpu_info} ✓")
            return True
        log.warning("nvidia-smi returned non-zero exit code")
        return False

    except FileNotFoundError:
        log.warning(
            "nvidia-smi not found. "
            "Install NVIDIA drivers: https://www.nvidia.com/drivers"
        )
        return False
    except subprocess.TimeoutExpired:
        log.warning("nvidia-smi timed out")
        return False
    except Exception as e:
        log.warning(f"CUDA check error: {e}")
        return False


def check_mps() -> bool:
    """
    Check Apple Silicon MPS availability.
    Only relevant on macOS arm64.
    Returns True if MPS is available.
    """
    if not IS_APPLE_SILICON:
        return False

    try:
        import torch
        if torch.backends.mps.is_available():
            log.info("Apple Silicon MPS ✓")
            return True
        log.warning("MPS not available (macOS arm64 detected but MPS unavailable)")
        return False
    except ImportError:
        log.warning("PyTorch not installed — cannot check MPS")
        return False
    except AttributeError:
        log.warning("PyTorch version too old for MPS support (need 1.12+)")
        return False


def check_torch() -> bool:
    """
    Check PyTorch installation and appropriate acceleration.

    Windows/Linux: expects CUDA
    macOS arm64:   expects MPS
    macOS x86:     CPU only (warns)
    Returns True if torch is installed (regardless of acceleration).
    """
    try:
        import torch
        version = torch.__version__
    except ImportError:
        log.warning("PyTorch not installed")
        return False

    # --- Windows / Linux: need CUDA ---
    if IS_WINDOWS or IS_LINUX:
        if torch.cuda.is_available():
            try:
                device_name = torch.cuda.get_device_name(0)
                props       = torch.cuda.get_device_properties(0)
                vram        = getattr(props, "total_memory", 0) / (1024 ** 3)
                log.info(
                    f"PyTorch {version} — CUDA: {device_name} "
                    f"({vram:.1f} GB VRAM) ✓"
                )
            except Exception:
                log.info(f"PyTorch {version} — CUDA ✓")
            return True

        # Torch installed but no CUDA
        log.error(
            f"PyTorch {version} installed but CUDA unavailable. "
            f"Reinstall with CUDA support:\n"
            f"  {sys.executable} -m pip install torch torchvision torchaudio "
            f"--index-url https://download.pytorch.org/whl/cu121"
        )
        return False

    # --- macOS arm64: prefer MPS ---
    if IS_APPLE_SILICON:
        if torch.backends.mps.is_available():
            log.info(f"PyTorch {version} — MPS (Apple Silicon) ✓")
            return True
        log.warning(
            f"PyTorch {version} installed but MPS unavailable. "
            f"Update macOS to 12.3+ and PyTorch to 1.12+"
        )
        # Still return True — CPU fallback is usable
        return True

    # --- macOS x86 or other ---
    log.warning(
        f"PyTorch {version} — CPU only "
        f"(no GPU acceleration on this platform)"
    )
    return True


def check_whisperx() -> bool:
    """
    Check whisperx and faster-whisper are installed.
    Returns True if both are importable.
    """
    whisperx_ok      = False
    faster_whisper_ok = False

    try:
        import whisperx  # noqa: F401
        whisperx_ok = True
    except ImportError:
        log.warning("whisperx not installed")

    try:
        import faster_whisper  # noqa: F401
        faster_whisper_ok = True
    except ImportError:
        log.warning("faster-whisper not installed")

    if whisperx_ok and faster_whisper_ok:
        try:
            import whisperx as wx
            version = getattr(wx, "__version__", "unknown")
            log.info(f"whisperx {version} + faster-whisper ✓")
        except Exception:
            log.info("whisperx + faster-whisper ✓")
        return True

    return False


def check_argos() -> bool:
    """Check argostranslate is installed."""
    try:
        import argostranslate.translate  # noqa: F401
        log.info("argostranslate ✓")
        return True
    except ImportError:
        log.warning("argostranslate not installed")
        return False


def check_fastapi() -> bool:
    """Check FastAPI + uvicorn + python-multipart are installed."""
    missing = []

    for package, import_name in [
        ("fastapi",           "fastapi"),
        ("uvicorn",           "uvicorn"),
        ("python-multipart",  "multipart"),
    ]:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(package)

    if not missing:
        log.info("FastAPI + uvicorn + python-multipart ✓")
        return True

    log.warning(f"Missing web server packages: {', '.join(missing)}")
    return False


def check_pip() -> bool:
    """Verify pip is available."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            version_str = result.stdout.strip().split(",")[0]
            log.info(f"pip: {version_str} ✓")
            return True
    except Exception:
        pass

    log.error("pip not available")
    return False


def upgrade_pip() -> None:
    """Silently upgrade pip to latest version."""
    log.info("Upgrading pip...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
        capture_output=True,
    )


# ============================================================================
# @block LOCAL:SETUP:002 @desc Pre-torch device detection (setup wizard only)
# ============================================================================

def _detect_device_pre_torch() -> str:
    """
    Detect GPU presence WITHOUT torch.
    Used in setup wizard Step 1 — before torch is installed.

    Uses nvidia-smi directly on Windows/Linux.
    Checks Apple Silicon via platform on macOS.

    Returns "cuda" | "mps" | "cpu"
    """
    # --- Apple Silicon — detectable without torch ---
    if IS_APPLE_SILICON:
        log.info("Device: MPS (Apple Silicon) — detected via platform")
        return "mps"

    # --- NVIDIA via nvidia-smi --- 
    if not IS_MACOS:
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name",
                    "--format=csv,noheader",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                gpu_name = result.stdout.strip().split("\n")[0]
                log.info(
                    f"Device: CUDA — {gpu_name} "
                    f"(detected via nvidia-smi)"
                )
                return "cuda"
        except FileNotFoundError:
            log.warning(
                "nvidia-smi not found. "
                "Install NVIDIA drivers: https://www.nvidia.com/drivers"
            )
        except subprocess.TimeoutExpired:
            log.warning("nvidia-smi timed out")
        except Exception as e:
            log.warning(f"nvidia-smi check failed: {e}")

    return "cpu"

# ============================================================================
# @block LOCAL:SETUP:002 @desc Preflight summary (used at server start)
# ============================================================================

def run_preflight() -> bool:
    """
    Run all dependency checks before starting the server.
    Prints a grouped summary and returns True only if
    all required dependencies are satisfied.

    Required:   Python, torch, whisperx, fastapi, ffmpeg
    Optional:   argostranslate (translation), GPU acceleration
    """
    print()
    ok = True

    # Python
    if not check_python_version():
        ok = False

    # GPU / acceleration
    device = detect_device()
    if device == "cpu":
        print(
            "  ⚠  No GPU acceleration. "
            "Processing will work but will be significantly slower."
        )

    # ffmpeg
    if not check_ffmpeg():
        log.error("ffmpeg not found")
        if IS_WINDOWS:
            print("  Run: python subtitler_local.py --setup")
        else:
            print("  macOS:  brew install ffmpeg")
            print("  Linux:  sudo apt install ffmpeg")
        ok = False

    # PyTorch
    if not check_torch():
        print("  Run: python subtitler_local.py --setup")
        ok = False

    # WhisperX
    if not check_whisperx():
        print("  Run: python subtitler_local.py --setup")
        ok = False

    # FastAPI
    if not check_fastapi():
        print(
            f"  Run: {sys.executable} -m pip install "
            f"fastapi uvicorn[standard] python-multipart"
        )
        ok = False

    # Argos (optional — warn only)
    if not check_argos():
        log.warning("argostranslate not installed — translation unavailable")

    return ok

# ============================================================================
# @block LOCAL:SETUP:003 @desc pip helpers
# ============================================================================

def pip_install(
    packages: list[str] | str,
    index_url: str | None = None,
    extra_index_url: str | None = None,
    quiet: bool = False,
) -> bool:
    """
    Install one or more packages via pip.
    Always uses 'python -m pip' to avoid PATH issues.

    Args:
        packages:         package name(s)
        index_url:        --index-url (replaces PyPI)
        extra_index_url:  --extra-index-url (added alongside PyPI)
        quiet:            suppress pip output

    Returns True if exit code == 0.
    """
    if isinstance(packages, str):
        packages = [packages]

    cmd = [sys.executable, "-m", "pip", "install", "--upgrade"] + packages

    if index_url:
        cmd += ["--index-url", index_url]
    if extra_index_url:
        cmd += ["--extra-index-url", extra_index_url]
    if quiet:
        cmd += ["--quiet"]

    display = [p for p in packages if not p.startswith("-")]
    log.info(f"Installing: {' '.join(display)}")

    result = subprocess.run(cmd)
    return result.returncode == 0


def pip_uninstall(packages: list[str] | str) -> None:
    """Silently uninstall packages (best-effort, no error on missing)."""
    if isinstance(packages, str):
        packages = [packages]
    subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "-y"] + packages,
        capture_output=True,
    )


# ============================================================================
# @block LOCAL:SETUP:004 @desc PyTorch installation
# ============================================================================

# CUDA wheel index URLs in preference order
_CUDA_INDEX_URLS = [
    "https://download.pytorch.org/whl/cu126",
    "https://download.pytorch.org/whl/cu124",
    "https://download.pytorch.org/whl/cu121",
    "https://download.pytorch.org/whl/cu118",
]

_TORCH_PACKAGES = ["torch", "torchvision", "torchaudio"]


def install_torch() -> bool:
    """
    Install PyTorch with appropriate acceleration backend.

    Windows / Linux:  CUDA wheels (tries cu126 → cu124 → cu121)
    macOS arm64:      Standard PyPI wheel (includes MPS support)
    macOS x86 / other: Standard PyPI wheel (CPU only)

    Returns True on success.
    """

    # ------------------------------------------------------------ macOS
    if IS_MACOS:
        print("\n  Installing PyTorch (macOS)...")
        if IS_APPLE_SILICON:
            print("  MPS acceleration will be available (Apple Silicon) ✓")
        else:
            print("  Note: CPU only on Intel Mac (no GPU acceleration)")
        print()

        # Standard PyPI torch already includes MPS on macOS
        ok = pip_install(_TORCH_PACKAGES)
        if ok:
            log.info("PyTorch installed ✓")
        return ok

    # -------------------------------------------- Windows / Linux CUDA
    print("\n  Installing PyTorch with CUDA support...")
    print("  This may take several minutes (~3 GB download)\n")

    # Remove CPU-only version first to avoid mixed installs
    pip_uninstall(_TORCH_PACKAGES)

    for index_url in _CUDA_INDEX_URLS:
        cuda_tag = index_url.split("/")[-1]   # e.g. "cu121"
        log.info(f"Trying PyTorch {cuda_tag}...")

        result = subprocess.run([
            sys.executable, "-m", "pip", "install",
            *_TORCH_PACKAGES,
            "--index-url", index_url,
        ])

        if result.returncode == 0:
            log.info(f"PyTorch installed with {cuda_tag} ✓")
            return True

        log.warning(f"PyTorch {cuda_tag} failed, trying next...")

    # All CUDA attempts failed
    print("\n  ✗ Automatic CUDA installation failed.")
    print("\n  Manual installation:")
    print("    1. Visit: https://pytorch.org/get-started/locally/")
    print("    2. Select: Stable → Windows → Pip → Python → CUDA 12.x")
    print("    3. Run the generated command, e.g.:")
    print(
        f"       {sys.executable} -m pip install torch torchvision torchaudio"
        f" --index-url https://download.pytorch.org/whl/cu121"
    )
    return False


def verify_torch_after_install() -> bool:
    """
    Verify PyTorch + acceleration after installation.
    Handles the case where newly installed packages need
    a fresh import (importlib.reload is unreliable for torch).

    Returns True if torch is usable, False if restart needed.
    """
    try:
        # Force reimport if already loaded in this session
        if "torch" in sys.modules:
            import importlib
            importlib.reload(sys.modules["torch"])

        import torch

        if IS_WINDOWS or IS_LINUX:
            if torch.cuda.is_available():
                log.info(f"PyTorch CUDA verified: {torch.cuda.get_device_name(0)} ✓")
                return True
            # Installed but CUDA not detected yet — likely needs restart
            return False

        if IS_APPLE_SILICON:
            if torch.backends.mps.is_available():
                log.info("PyTorch MPS verified ✓")
                return True
            # MPS not available but torch works — CPU fallback acceptable
            log.warning("MPS unavailable after install — will use CPU")
            return True

        return True  # macOS x86 / other — CPU is expected

    except ImportError:
        return False


# ============================================================================
# @block LOCAL:SETUP:005 @desc WhisperX installation
# ============================================================================

def install_whisperx() -> bool:
    """
    Install whisperx and its core dependencies.

    Dependency chain:
        whisperx
            └── faster-whisper
                    └── ctranslate2
        whisperx
            └── transformers   (alignment models)
            └── torchaudio     (audio processing)

    Note: torch must be installed BEFORE whisperx so that
    ctranslate2 picks up the correct CUDA runtime.

    Returns True on success.
    """
    print("\n  Installing whisperx + faster-whisper...\n")

    # ctranslate2 must match the installed CUDA version.
    # Installing it explicitly before whisperx avoids version conflicts.
    log.info("Installing ctranslate2...")
    if not pip_install("ctranslate2"):
        log.warning("ctranslate2 install failed — whisperx may still work")

    # Core whisperx (pulls faster-whisper, transformers, etc.)
    if not pip_install("whisperx"):
        print("\n  ✗ whisperx installation failed.")
        print("\n  Try manually:")
        print(f"    {sys.executable} -m pip install whisperx")
        print("\n  If the error mentions ctranslate2 or CUDA:")
        print(f"    {sys.executable} -m pip install ctranslate2 --upgrade")
        print(f"    {sys.executable} -m pip install whisperx")
        return False

    # Verify both imports work
    if check_whisperx():
        return True

    print("\n  ✗ whisperx installed but import failed.")
    print("  Check logs above for details.")
    return False


# ============================================================================
# @block LOCAL:SETUP:006 @desc Optional packages installation
# ============================================================================

def install_argos() -> bool:
    """
    Install argostranslate (offline translation engine).
    Optional — server works without it (no translation).
    Returns True on success.
    """
    print("\n  Installing argostranslate...\n")
    ok = pip_install("argostranslate")
    if ok:
        log.info("argostranslate installed ✓")
    return ok


def install_fastapi() -> bool:
    """
    Install FastAPI + uvicorn + python-multipart.
    Required for the HTTP server.
    Returns True on success.
    """
    print("\n  Installing FastAPI + uvicorn + python-multipart...\n")
    ok = pip_install(["fastapi", "uvicorn[standard]", "python-multipart"])
    if ok:
        log.info("FastAPI stack installed ✓")
    return ok


# ============================================================================
# @block LOCAL:SETUP:007 @desc Installation health check (post-install)
# ============================================================================

def check_installation() -> dict[str, bool]:
    """
    Run all dependency checks and return a status dictionary.
    Used by Setup.bat / subtitler_local.sh to decide
    whether setup wizard is needed.

    Returns:
        {
            "python":    bool,
            "ffmpeg":    bool,
            "torch":     bool,
            "whisperx":  bool,
            "fastapi":   bool,
            "argos":     bool,   # optional
        }
    """
    return {
        "python":   check_python_version(),
        "ffmpeg":   check_ffmpeg(),
        "torch":    check_torch(),
        "whisperx": check_whisperx(),
        "fastapi":  check_fastapi(),
        "argos":    check_argos(),  
    }


def is_fully_installed(status: dict[str, bool]) -> bool:
    """
    Returns True if all REQUIRED dependencies are satisfied.
    argos is optional and does not block server start.
    """
    required = ["python", "ffmpeg", "torch", "whisperx", "fastapi"]
    return all(status.get(k, False) for k in required)


def print_installation_status(status: dict[str, bool]) -> None:
    """Print a formatted installation status table."""
    labels = {
        "python":   "Python 3.9+",
        "ffmpeg":   "ffmpeg",
        "torch":    "PyTorch (CUDA/MPS)",
        "whisperx": "whisperx + faster-whisper",
        "fastapi":  "FastAPI + uvicorn",
        "argos":    "argostranslate (optional)",
    }
    optional = {"argos"}

    print()
    print("  Dependency status:")
    print("  " + "-" * 40)
    for key, label in labels.items():
        state = status.get(key, False)
        mark  = "✓" if state else ("○" if key in optional else "✗")
        tag   = "" if state else (" [optional]" if key in optional else " [REQUIRED]")
        print(f"  {mark}  {label}{tag}")
    print("  " + "-" * 40)
    print()

# ============================================================================
# @block LOCAL:MODELS:001 @desc faster-whisper model cache
# ============================================================================

# faster-whisper скачивает модели с HuggingFace в формате CTranslate2.
# Модели хранятся в ~/.cache/huggingface/hub/models--Systran--faster-whisper-*/
# Каждая модель — отдельная директория со snapshots/

_WHISPERX_HF_REPO_PREFIXES = [
    "models--Systran--faster-whisper-",       # official
    "models--mobiuslabsgmbh--faster-whisper-", # alternative
    "models--guillaumekln--faster-whisper-",   # legacy
]

def get_installed_whisper_models() -> list[str]:
    installed = []
    if not WHISPERX_CACHE_DIR.exists():
        return installed
    try:
        for entry in WHISPERX_CACHE_DIR.iterdir():
            if not entry.is_dir():
                continue

            # Check against all known repo prefixes
            model_name = None
            for prefix in _WHISPERX_HF_REPO_PREFIXES:
                if entry.name.startswith(prefix):
                    model_name = entry.name[len(prefix):]
                    break

            if model_name is None:
                continue

            if model_name in WHISPER_MODELS and _model_has_snapshots(entry):
                installed.append(model_name)

    except PermissionError as e:
        log.warning(f"Cannot read model cache: {e}")

    return [m for m in WHISPER_MODELS if m in installed]


def _model_has_snapshots(model_dir: Path) -> bool:
    """
    Verify model directory contains at least one complete snapshot.
    A valid snapshot contains model.bin (the CTranslate2 weights).
    """
    snapshots_dir = model_dir / "snapshots"
    if not snapshots_dir.exists():
        return False

    try:
        for snapshot in snapshots_dir.iterdir():
            if snapshot.is_dir():
                # Check for the main weights file
                if (snapshot / "model.bin").exists():
                    return True
    except PermissionError:
        pass

    return False


def download_whisper_model(model_name: str, device: str = "cpu") -> bool:
    ...
    try:
        import whisperx

        model = whisperx.load_model(
            model_name,
            device=device,
            compute_type="int8",
            download_root=None,
        )
        del model

        log.info(f"Model '{model_name}' ready ✓")
        return True

    except ImportError as e:
        err = str(e)

        # torch/whisperx version incompatibility
        if "mark_subclass_constructor_exportable_experimental" in err \
                or "_export" in err:
            log.error(
                f"PyTorch version is incompatible with whisperx.\n"
                f"  Installed torch is too new for current whisperx version.\n"
                f"\n"
                f"  Fix — reinstall compatible PyTorch:\n"
                f"    pip uninstall torch torchvision torchaudio -y\n"
                f"    pip install torch==2.8.0 torchvision==0.23.0 "
                f"torchaudio==2.8.0 "
                f"--index-url https://download.pytorch.org/whl/cu126\n"
                f"\n"
                f"  Then re-run setup:\n"
                f"    python subtitler_local.py --setup\n"
                f"\n"
                f"  Check compatible versions:\n"
                f"    pip show torch whisperx faster-whisper"
            )
        else:
            log.error(f"Model download failed (ImportError): {e}")

        return False

    except Exception as e:
        err = str(e)

        # Same error may surface as generic Exception on some platforms
        if "mark_subclass_constructor_exportable_experimental" in err \
                or "_export" in err:
            log.error(
                f"PyTorch version is incompatible with whisperx.\n"
                f"  Fix — reinstall compatible PyTorch:\n"
                f"    pip uninstall torch torchvision torchaudio -y\n"
                f"    pip install torch==2.8.0 torchvision==0.23.0 "
                f"torchaudio==2.8.0 "
                f"--index-url https://download.pytorch.org/whl/cu126\n"
                f"\n"
                f"  Then re-run: python subtitler_local.py --setup"
            )
        else:
            log.error(f"Model download failed: {e}")
            log.info("If download stalls, check: https://huggingface.co/Systran")

        return False


# ============================================================================
# @block LOCAL:MODELS:002 @desc Alignment model cache
# ============================================================================

# WhisperX alignment models are wav2vec2 / other transformer models
# stored in HuggingFace cache under various repo names depending on language.
# The mapping is defined inside whisperx itself (whisperx/alignment.py).
#
# We mirror the same language→model mapping here for cache inspection
# without importing whisperx at module level.

_ALIGNMENT_MODEL_MAP = {
    # lang_code: HuggingFace repo name
    "en": "WAV2VEC2_ASR_BASE_960H",                          # torchaudio bundle
    "fr": "VOXPOPULI_ASR_BASE_10K_FR",
    "de": "VOXPOPULI_ASR_BASE_10K_DE",
    "es": "VOXPOPULI_ASR_BASE_10K_ES",
    "it": "VOXPOPULI_ASR_BASE_10K_IT",
    "ja": "jonatasgrosman/wav2vec2-large-xlsr-53-japanese",
    "zh": "jonatasgrosman/wav2vec2-large-xlsr-53-chinese-zh-cn",
    "nl": "VOXPOPULI_ASR_BASE_10K_NL",
    "uk": "Yehor/wav2vec2-xls-r-300m-uk-with-small-lm",
    "pt": "jonatasgrosman/wav2vec2-large-xlsr-53-portuguese",
    "ar": "jonatasgrosman/wav2vec2-large-xlsr-53-arabic",
    "cs": "comodoro/wav2vec2-xls-r-300m-cs-250",
    "ru": "jonatasgrosman/wav2vec2-large-xlsr-53-russian",
    "pl": "jonatasgrosman/wav2vec2-large-xlsr-53-polish",
    "hu": "jonatasgrosman/wav2vec2-large-xlsr-53-hungarian",
    "fi": "jonatasgrosman/wav2vec2-large-xlsr-53-finnish",
    "fa": "jonatasgrosman/wav2vec2-large-xlsr-53-persian",
    "el": "jonatasgrosman/wav2vec2-large-xlsr-53-greek",
    "tr": "mpoyraz/wav2vec2-xls-r-300m-cv8-turkish",
    "da": "saattrupdan/wav2vec2-xls-r-300m-ftspeech",
    "he": "imvladikon/wav2vec2-xls-r-300m-hebrew",
    "vi": "nguyenvulebinh/wav2vec2-base-vi",
    "ko": "kresnik/wav2vec2-large-xlsr-korean",
    "ur": "kingabzpro/wav2vec2-large-xls-r-300m-Urdu",
    "te": "anuragshas/wav2vec2-large-xlsr-53-telugu",
    "hi": "theainerd/Wav2Vec2-large-xlsr-hindi",
    "ca": "softcatala/wav2vec2-large-xlsr-catala",
    "ml": "gvs/wav2vec2-large-xlsr-malayalam",
}


def get_alignment_model_repo(lang_code: str) -> str | None:
    """
    Return HuggingFace repo name for alignment model of given language.
    Returns None if language has no alignment model support.
    """
    return _ALIGNMENT_MODEL_MAP.get(lang_code)


def is_alignment_model_cached(lang_code: str) -> bool:
    """
    Check if alignment model for lang_code is already in HF cache.
    Looks for the model directory in ~/.cache/huggingface/hub/.
    """
    repo = get_alignment_model_repo(lang_code)
    if not repo:
        return False

    # torchaudio bundles (e.g. WAV2VEC2_ASR_BASE_960H) are not in HF cache
    if repo.startswith("WAV2VEC2_") or repo.startswith("VOXPOPULI_"):
        # These are downloaded by torchaudio into its own cache
        # Treat as "always available" if torchaudio is installed
        try:
            import torchaudio  # noqa: F401
            return True
        except ImportError:
            return False

    # HuggingFace hosted models
    # Repo name format: "owner/model-name"
    # Cache dir format: "models--owner--model-name"
    if "/" in repo:
        owner, model = repo.split("/", 1)
        cache_name   = f"models--{owner}--{model}"
        cache_path   = ALIGNMENT_CACHE_DIR / cache_name
        return cache_path.exists() and any(cache_path.iterdir())

    return False


def get_installed_alignment_langs() -> list[str]:
    """
    Return list of language codes whose alignment models are cached locally.
    """
    return [
        lang for lang in _ALIGNMENT_MODEL_MAP
        if is_alignment_model_cached(lang)
    ]


def download_alignment_model(lang_code: str, device: str = "cpu") -> bool:
    """
    Download alignment model for a specific language via whisperx.

    Called automatically during transcription if model is missing.
    Can also be called explicitly during setup.

    Args:
        lang_code: ISO 639-1 language code (e.g. "ru", "ja")
        device:    compute device string

    Returns True on success, False if language not supported or download failed.
    """
    if lang_code not in WHISPERX_ALIGNMENT_LANGUAGES:
        log.info(
            f"No alignment model available for '{lang_code}' — "
            f"will use segment-level timestamps"
        )
        return False

    if is_alignment_model_cached(lang_code):
        log.info(f"Alignment model '{lang_code}' already cached ✓")
        return True

    repo = get_alignment_model_repo(lang_code)
    log.info(
        f"Downloading alignment model for '{lang_code}' "
        f"({repo or 'torchaudio bundle'})..."
    )

    try:
        import whisperx

        # load_align_model triggers HuggingFace download if not cached
        model, metadata = whisperx.load_align_model(
            language_code=lang_code,
            device=device,
        )

        # Free memory immediately — we only wanted the download
        del model, metadata

        log.info(f"Alignment model '{lang_code}' ready ✓")
        return True

    except Exception as e:
        log.warning(
            f"Alignment model download failed for '{lang_code}': {e}\n"
            f"  Transcription will continue without word-level alignment."
        )
        return False


# ============================================================================
# @block LOCAL:MODELS:003 @desc Model info display
# ============================================================================

def print_models_table(show_alignment: bool = False) -> None:
    """
    Print formatted table of Whisper models with install status.

    Args:
        show_alignment: if True, also show alignment model status per language
    """
    installed = get_installed_whisper_models()

    print("\n  Whisper models:")
    print("  " + "-" * 44)
    print(f"  {'Model':<16} {'Size':>10}   {'Status'}")
    print("  " + "-" * 44)

    for model in WHISPER_MODELS:
        size   = WHISPER_MODEL_SIZES.get(model, "")
        status = "✓ installed" if model in installed else "not downloaded"
        print(f"  {model:<16} {size:>10}   {status}")

    print("  " + "-" * 44)
    print(f"  Cache: {WHISPERX_CACHE_DIR}")

    if show_alignment:
        print("\n  Alignment models (word-level timestamps):")
        print("  " + "-" * 44)

        cached_langs    = get_installed_alignment_langs()
        supported_langs = sorted(WHISPERX_ALIGNMENT_LANGUAGES)

        for lang in supported_langs:
            status = "✓ cached" if lang in cached_langs else "auto-download on use"
            print(f"  {lang:<8} {status}")

        unsupported = sorted(
            set(_ALIGNMENT_MODEL_MAP.keys()) - WHISPERX_ALIGNMENT_LANGUAGES
        )
        if unsupported:
            print(f"\n  No alignment support: {', '.join(unsupported)}")

        print("  " + "-" * 44)

# ============================================================================
# @block LOCAL:SETUP:008 @desc Interactive setup wizard
# ============================================================================

def run_setup() -> None:
    """
    Interactive setup wizard.
    Checks all dependencies, installs what is missing.

    Steps:
        1. System requirements  (Python, GPU, ffmpeg, pip)
        2. Python packages      (torch, whisperx, argos, fastapi)
        3. Whisper models       (download via faster-whisper)
        4. Translation langs    (argostranslate packages)
        5. Summary + next steps
    """
    print("=" * 60)
    print(f"  Subtitler Local v{SCRIPT_VERSION} — Setup Wizard")
    print(f"  Platform: {PLATFORM} "
          f"{'(Apple Silicon)' if IS_APPLE_SILICON else ''}")
    print("=" * 60)

    # ================================================================
    # STEP 1 — System requirements
    # ================================================================
    print("\n[1/5] Checking system requirements...\n")

    # Python version
    if not check_python_version():
        print("\n  ✗ Python 3.9+ is required.")
        print("    Download: https://www.python.org/downloads/")
        sys.exit(1)

        # GPU detection via nvidia-smi (no torch needed at this stage)
    device = _detect_device_pre_torch()
    if device == "cuda":
        check_cuda()
    elif device == "mps":
        check_mps()
    else:
        print(
            "\n  ⚠  No GPU detected. Processing will use CPU.\n"
            "     Transcription will work but will be significantly slower.\n"
            "     Recommended: NVIDIA GPU (Windows/Linux) or Apple Silicon (macOS).\n"
            "\n  Note: if you have an NVIDIA GPU, this may resolve after\n"
            "     PyTorch installation in Step 2."
        )
        answer = input("\n  Continue? [Y/n]: ").strip().lower()
        if answer not in ("", "y", "yes"):
            print("  Setup cancelled.")
            sys.exit(0)

    # ffmpeg
    print()
    if check_ffmpeg():
        pass  # already logged OK inside check_ffmpeg
    else:
        _setup_ffmpeg()

    # pip
    print()
    if not check_pip():
        print(
            "\n  ✗ pip is required.\n"
            f"    Run: {sys.executable} -m ensurepip --upgrade"
        )
        sys.exit(1)

    upgrade_pip()
    fix_scripts_path()

    # ================================================================
    # STEP 2 — Python packages
    # ================================================================
    print("\n[2/5] Checking Python packages...\n")

    # --- PyTorch ---
    if check_torch():
        pass  # already logged OK
    else:
        _setup_torch(device)

    # Re-detect device now that torch is installed
    # Replaces the pre-torch estimate with accurate detection
    device = detect_device()
    log.info(f"Device confirmed: {device_display_name(device)}")

    # --- WhisperX ---
    if check_whisperx():
        pass  # already logged OK
    else:
        _setup_whisperx()

    # --- argostranslate (optional) ---
    if check_argos():
        pass  # already logged OK
    else:
        _setup_argos()

    # --- FastAPI ---
    if check_fastapi():
        pass  # already logged OK
    else:
        _setup_fastapi()

    # ================================================================
    # STEP 3 — Whisper models
    # ================================================================
    print("\n[3/5] Whisper models...\n")
    print_models_table()

    installed_models = get_installed_whisper_models()

    if not installed_models:
        # Offer tiny first as default
        size   = WHISPER_MODEL_SIZES["tiny"]
        answer = input(
            f"\n  No models found. Download 'tiny' ({size})? [Y/n]: "
        ).strip().lower()

        if answer in ("", "y", "yes"):
            download_whisper_model("tiny", device="cpu")
            installed_models = get_installed_whisper_models()
        else:
            # User skipped tiny — go directly to manual selection
            # Do NOT show warning yet — user can still pick another model
            print(
                f"\n  Skipped 'tiny'. "
                f"You can select another model below."
            )
    else:
        print(f"\n  Installed: {', '.join(installed_models)}")

    # Loop — offer any model download regardless of tiny choice
    while True:
        # Refresh installed list on each iteration
        installed_models = get_installed_whisper_models()

        print(f"\n  Available: {', '.join(WHISPER_MODELS)}")

        # Show currently installed inline
        if installed_models:
            print(f"  Installed: {', '.join(installed_models)}")

        extra = input(
            "  Download a model? (enter name or press Enter to skip): "
        ).strip().lower()

        if not extra:
            # User pressed Enter — check if anything is installed at all
            installed_models = get_installed_whisper_models()
            if not installed_models:
                # Now show the warning — after user explicitly chose to skip
                print(
                    "\n  ⚠  No model downloaded.\n"
                    "     The server will attempt to download the default\n"
                    f"    model '{DEFAULT_MODEL}' on first transcription request.\n"
                    "     This requires an internet connection at that time."
                )
            break

        if extra in WHISPER_MODELS:
            if extra in installed_models:
                print(f"  '{extra}' is already installed ✓")
            else:
                download_whisper_model(extra, device="cpu")
                # Refresh immediately so next iteration shows updated list
                installed_models = get_installed_whisper_models()
        else:
            print(
                f"  Unknown model '{extra}'.\n"
                f"  Available: {', '.join(WHISPER_MODELS)}"
            )

    # ================================================================
    # STEP 4 — Translation languages
    # ================================================================
    print("\n[4/5] Translation languages (argostranslate)...\n")

    if not check_argos():
        print("  argostranslate not installed — skipping.")
        print("  To enable translation, re-run setup and install argostranslate.")
    else:
        installed_pairs = get_argos_installed_languages()
        if installed_pairs:
            print(f"  Installed pairs: {', '.join(installed_pairs)}")
        else:
            print("  No translation packages installed yet.")

        while True:
            answer = input(
                "\n  Install a language? "
                "(e.g. 'ru', 'es', 'de' — or press Enter to skip): "
            ).strip().lower()
            if not answer:
                break
            install_argos_language(answer)

    # ================================================================
    # STEP 5 — Summary
    # ================================================================
    print("\n[5/5] Setup complete!")
    print("=" * 60)

    # Refresh state for summary
    final_models    = get_installed_whisper_models()
    final_langs     = get_argos_installed_languages() if check_argos() else []
    final_device    = device_display_name(detect_device())

    # Alignment info
    cached_align    = get_installed_alignment_langs()
    align_note      = (
        f"{', '.join(cached_align)}" if cached_align
        else "none cached (auto-download on first use per language)"
    )

    print(f"\n  Device:           {final_device}")
    print(f"  ffmpeg:           {FFMPEG_PATH}")
    print(
        f"  Whisper models:   "
        f"{', '.join(final_models) if final_models else 'none (auto-download on first use)'}"
    )
    print(
        f"  Alignment models: {align_note}"
    )
    print(
        f"  Translation:      "
        f"{', '.join(final_langs) if final_langs else 'none'}"
    )

    # How to start
    print(f"\n  Start the server:")
    print(f"    python subtitler_local.py")

    if final_models:
        best = final_models[-1]
        print(f"    python subtitler_local.py --model {best}")

    if IS_WINDOWS:
        print(f"    Subtitler_Local.bat")
    else:
        print(f"    bash subtitler_local.sh")

    # AE plugin settings
    print(f"\n  After Effects plugin settings:")
    print(f"    Server URL : http://localhost:{DEFAULT_PORT}")
    print(f"    Mode       : Direct")
    print(f"    API Key    : local")
    print("=" * 60)


# ============================================================================
# @block LOCAL:SETUP:009 @desc Setup sub-routines (called from wizard steps)
# ============================================================================

def _setup_ffmpeg() -> None:
    """
    Handle missing ffmpeg inside setup wizard.
    Exits setup on Windows if user declines auto-install.
    On macOS/Linux prints manual instructions and exits.
    """
    if not install_ffmpeg():
        if IS_WINDOWS:
            print("\n  ✗ ffmpeg is required. Setup cannot continue.")
            sys.exit(1)
        else:
            # macOS/Linux: install_ffmpeg already printed instructions
            print(
                "\n  ✗ Please install ffmpeg and re-run setup:\n"
                f"    python subtitler_local.py --setup"
            )
            sys.exit(1)


def _setup_torch(device: str) -> None:
    """
    Handle missing / broken PyTorch inside setup wizard.
    Exits on failure since torch is required.
    """
    prompt = "\n  Install PyTorch"
    if device == "cuda":
        prompt += " with CUDA support? (~3 GB) [Y/n]: "
    elif device == "mps":
        prompt += " (with MPS support)? [Y/n]: "
    else:
        prompt += " (CPU mode)? [Y/n]: "

    answer = input(prompt).strip().lower()
    if answer not in ("", "y", "yes"):
        print("  ✗ PyTorch is required. Setup cancelled.")
        sys.exit(0)

    if not install_torch():
        print("\n  ✗ PyTorch installation failed.")
        sys.exit(1)

    # Verify without restarting if possible
    if not verify_torch_after_install():
        print(
            "\n  ⚠  PyTorch installed but acceleration check requires restart.\n"
            "  Please re-run setup:\n"
            f"    python subtitler_local.py --setup"
        )
        sys.exit(0)


def _setup_whisperx() -> None:
    """
    Handle missing whisperx inside setup wizard.
    Exits on failure since whisperx is required.
    """
    answer = input(
        "\n  Install whisperx + faster-whisper? [Y/n]: "
    ).strip().lower()

    if answer not in ("", "y", "yes"):
        print("  ✗ whisperx is required. Setup cancelled.")
        sys.exit(0)

    if not install_whisperx():
        print("\n  ✗ whisperx installation failed.")
        sys.exit(1)


def _setup_argos() -> None:
    """
    Handle missing argostranslate inside setup wizard.
    Optional — does not exit on failure or user decline.
    """
    answer = input(
        "\n  Install argostranslate (offline translation)? [Y/n]: "
    ).strip().lower()

    if answer in ("", "y", "yes"):
        if not install_argos():
            print(
                "  ⚠  argostranslate installation failed.\n"
                "     Translation will be unavailable.\n"
                "     You can install it later:\n"
                f"     {sys.executable} -m pip install argostranslate"
            )
        # Non-fatal — continue setup


def _setup_fastapi() -> None:
    """
    Handle missing FastAPI stack inside setup wizard.
    Exits on failure since FastAPI is required.
    """
    answer = input(
        "\n  Install FastAPI + uvicorn (web server)? [Y/n]: "
    ).strip().lower()

    if answer not in ("", "y", "yes"):
        print("  ✗ FastAPI is required. Setup cancelled.")
        sys.exit(0)

    if not install_fastapi():
        print("\n  ✗ FastAPI installation failed.")
        sys.exit(1)

# ============================================================================
# @block LOCAL:TRANSCRIBE:001 @desc Media utilities
# ============================================================================

def get_media_duration(file_path: str | Path) -> float:
    """
    Get media file duration in seconds via ffprobe.
    Returns 0.0 on any error.
    """
    try:
        result = subprocess.run(
            [
                FFPROBE_PATH,
                "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return float(result.stdout.strip())
    except (ValueError, subprocess.TimeoutExpired, Exception):
        return 0.0


# ============================================================================
# @block LOCAL:TRANSCRIBE:002 @desc WhisperX transcription pipeline
# ============================================================================

# compute_type matrix:
#   cuda  → "float16"  (best quality + speed on NVIDIA)
#   mps   → "float32"  (MPS does not support float16 in ctranslate2)
#   cpu   → "int8"     (fastest on CPU, acceptable quality)

_COMPUTE_TYPE = {
    "cuda": "float16",
    "mps":  "float32",
    "cpu":  "int8",
}


def _get_compute_type(device: str) -> str:
    return _COMPUTE_TYPE.get(device, "int8")


def transcribe(
    file_path: str | Path,
    model_name: str = "tiny",
    format_type: str = "standard",
    device: str | None = None,
) -> tuple[str, str]:
    import warnings

    # Suppress torchcodec warning — we use ffmpeg via whisperx.load_audio()
    # torchcodec is optional in whisperx, fallback works correctly
    warnings.filterwarnings(
        "ignore",
        message="torchcodec is not installed correctly",
        category=UserWarning,
    )
    warnings.filterwarnings(
        "ignore",
        message=".*libtorchcodec.*",
        category=UserWarning,
    )
    """
    Transcribe a media file using WhisperX pipeline:
        1. Load faster-whisper model
        2. Transcribe → segments with word timestamps
        3. Attempt alignment (word-level, per language)
           - auto-download alignment model if missing
           - graceful skip if language not supported
        4. Generate SRT from aligned (or unaligned) result

    Args:
        file_path:   path to audio/video file
        model_name:  whisper model name (e.g. "tiny", "large-v3")
        format_type: "standard" | "short" | "word"
        device:      "cuda" | "mps" | "cpu" | None (auto-detect)

    Returns:
        (srt_content, detected_language)
    """
    import whisperx

    if device is None:
        device = detect_device()

    compute_type = _get_compute_type(device)
    settings     = FORMAT_SETTINGS.get(format_type, FORMAT_SETTINGS["standard"])

    # ----------------------------------------------------------------
    # Stage 1 — Load model
    # ----------------------------------------------------------------
    log.info(
        f"Loading model '{model_name}' "
        f"[device={device}, compute={compute_type}]..."
    )

    try:
        model = whisperx.load_model(
            model_name,
            device=device,
            compute_type=compute_type,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to load Whisper model '{model_name}': {e}") from e

    # ----------------------------------------------------------------
    # Stage 2 — Transcription
    # ----------------------------------------------------------------
    log.info(f"Transcribing: {Path(file_path).name} [format={format_type}]")

    try:
        # whisperx.load_audio converts any ffmpeg-readable file to
        # a float32 numpy array at 16kHz mono
        audio = whisperx.load_audio(str(file_path))

        result = model.transcribe(
            audio,
            batch_size=_get_batch_size(device),
        )
    except Exception as e:
        raise RuntimeError(f"Transcription failed: {e}") from e
    finally:
        # Free GPU memory as soon as transcription is done
        _unload_model(model, device)

    detected_lang = result.get("language", "en")
    log.info(f"Detected language: {detected_lang}")

    # ----------------------------------------------------------------
    # Stage 3 — Alignment
    # ----------------------------------------------------------------
    result = _run_alignment(result, audio, detected_lang, device)

    # ----------------------------------------------------------------
    # Stage 4 — SRT generation
    # ----------------------------------------------------------------
    srt_content = generate_srt(result, settings)
    return srt_content, detected_lang


def _get_batch_size(device: str) -> int:
    """
    Batch size for whisperx transcription.

    Higher = faster but more VRAM.
    Safe defaults that work on most hardware:
        cuda → 16   (requires ~4 GB VRAM with medium model)
        mps  → 4    (MPS memory management is less predictable)
        cpu  → 1    (no batching benefit on CPU)
    """
    return {"cuda": 16, "mps": 4, "cpu": 1}.get(device, 1)


def _unload_model(model, device: str) -> None:
    """
    Free model from GPU/MPS memory after transcription.
    Prevents OOM errors when loading alignment model next.
    """
    try:
        del model
        if device == "cuda":
            import torch
            torch.cuda.empty_cache()
        elif device == "mps":
            import torch
            torch.mps.empty_cache()
    except Exception as e:
        log.debug(f"Model unload warning: {e}")


# ============================================================================
# @block LOCAL:TRANSCRIBE:003 @desc Alignment pipeline
# ============================================================================

def _run_alignment(
    result: dict,
    audio,
    lang_code: str,
    device: str,
) -> dict:
    """
    Attempt word-level alignment via whisperx.align().

    Alignment improves timestamp precision for ALL format types:
        - "word"     → each word gets exact start/end time
        - "short"    → short phrases tightly timed
        - "standard" → standard blocks with precise boundaries

    Failure modes handled gracefully:
        1. Language not in supported set          → skip, return original
        2. Alignment model download fails         → skip, return original
        3. PyTorch incompatible with whisperx     → skip, return original
        4. Alignment runtime error               → skip, return original

    In all skip cases transcription result is returned unchanged
    (segment-level timestamps from faster-whisper are still good).

    Returns result dict (aligned or original).
    """

    def _is_torch_compat_error(e: Exception) -> bool:
        """
        Detect PyTorch/whisperx version incompatibility.
        Surfaces as ImportError or generic Exception depending on platform.
        """
        err = str(e)
        return (
            "mark_subclass_constructor_exportable_experimental" in err
            or "_export" in err
        )

    def _log_torch_compat_warning() -> None:
        log.warning(
            "PyTorch version is incompatible with whisperx.\n"
            "  Alignment skipped — segment timestamps will be used.\n"
            "\n"
            "  Fix — reinstall compatible PyTorch:\n"
            "    pip uninstall torch torchvision torchaudio -y\n"
            "    pip install torch==2.8.0 torchvision==0.23.0 "
            "torchaudio==2.8.0 "
            "--index-url https://download.pytorch.org/whl/cu126\n"
            "\n"
            "  Then re-run setup:\n"
            "    python subtitler_local.py --setup"
        )

    # ----------------------------------------------------------------
    # Import whisperx
    # ----------------------------------------------------------------
    try:
        import whisperx
    except ImportError as e:
        if _is_torch_compat_error(e):
            _log_torch_compat_warning()
        else:
            log.warning(
                f"whisperx import failed: {e}\n"
                f"  Using segment timestamps as fallback."
            )
        return result

    # ----------------------------------------------------------------
    # Check language support
    # ----------------------------------------------------------------
    if lang_code not in WHISPERX_ALIGNMENT_LANGUAGES:
        log.info(
            f"Alignment not available for '{lang_code}' — "
            f"using segment timestamps"
        )
        return result

    # ----------------------------------------------------------------
    # Auto-download alignment model if not cached
    # ----------------------------------------------------------------
    if not is_alignment_model_cached(lang_code):
        log.info(
            f"Alignment model for '{lang_code}' not cached — "
            f"downloading..."
        )
        success = download_alignment_model(lang_code, device=device)
        if not success:
            log.warning(
                f"Alignment model unavailable for '{lang_code}' — "
                f"using segment timestamps"
            )
            return result

    # ----------------------------------------------------------------
    # Load alignment model
    # ----------------------------------------------------------------
    log.info(f"Loading alignment model for '{lang_code}'...")

    align_model    = None
    align_metadata = None

    try:
        align_model, align_metadata = whisperx.load_align_model(
            language_code=lang_code,
            device=device,
        )

    except ImportError as e:
        if _is_torch_compat_error(e):
            _log_torch_compat_warning()
        else:
            log.warning(
                f"Failed to load alignment model for '{lang_code}': {e}\n"
                f"  Using segment timestamps as fallback."
            )
        return result

    except Exception as e:
        if _is_torch_compat_error(e):
            _log_torch_compat_warning()
        else:
            log.warning(
                f"Failed to load alignment model for '{lang_code}': {e}\n"
                f"  Using segment timestamps as fallback."
            )
        return result

    # ----------------------------------------------------------------
    # Run alignment
    # ----------------------------------------------------------------
    log.info("Running word-level alignment...")

    try:
        aligned = whisperx.align(
            result["segments"],
            align_model,
            align_metadata,
            audio,
            device,
            return_char_alignments=False,
        )

        # Merge aligned segments back into result
        result["segments"]     = aligned.get("segments",     result["segments"])
        result["word_segments"] = aligned.get("word_segments", [])

        log.info("Word-level alignment complete ✓")

    except ImportError as e:
        if _is_torch_compat_error(e):
            _log_torch_compat_warning()
        else:
            log.warning(
                f"Alignment failed for '{lang_code}': {e}\n"
                f"  Using segment timestamps as fallback."
            )

    except Exception as e:
        if _is_torch_compat_error(e):
            _log_torch_compat_warning()
        else:
            log.warning(
                f"Alignment failed for '{lang_code}': {e}\n"
                f"  Using segment timestamps as fallback."
            )

    finally:
        # Always free alignment model memory
        try:
            if align_model is not None:
                del align_model
            if align_metadata is not None:
                del align_metadata
            if device == "cuda":
                import torch
                torch.cuda.empty_cache()
            elif device == "mps":
                import torch
                torch.mps.empty_cache()
        except Exception:
            pass

    return result


# ============================================================================
# @block LOCAL:TRANSCRIBE:004 @desc SRT generation (whisperx format)
# ============================================================================

def generate_srt(result: dict, settings: dict) -> str:
    """
    Generate SRT subtitle content from WhisperX result.

    WhisperX segment word format:
        {
            "start": float,
            "end":   float,
            "text":  str,
            "words": [
                {"word": str, "start": float, "end": float, "score": float},
                ...
            ]
        }

    Alignment is applied to ALL format types:
        "word"     → 1 word per subtitle, uses word["start"]/["end"]
        "short"    → 3 words / 1 line,   uses word timestamps
        "standard" → 6 words / 2 lines,  uses word timestamps

    If a word is missing timestamps (alignment gap) the previous
    word's end time is reused to avoid broken SRT entries.

    Args:
        result:   whisperx transcription result dict
        settings: FORMAT_SETTINGS entry

    Returns:
        SRT string.
    """
    max_words = settings.get("max_words_per_line", 6)
    max_lines = settings.get("max_line_count", 2)
    max_total = max_words * max_lines

    segments    = result.get("segments", [])
    srt_entries = []
    index       = 1

    for segment in segments:
        words = segment.get("words", [])

        # ---- No word-level data (alignment skipped or unavailable) ----
        if not words:
            text  = segment.get("text", "").strip()
            start = _safe_time(segment.get("start", 0))
            end   = _safe_time(segment.get("end",   0))

            if text:
                srt_entries.append(
                    _make_srt_entry(index, start, end, text)
                )
                index += 1
            continue

        # ---- Word-level timestamps available ----
        # Fill missing timestamps before chunking
        words = _fill_missing_timestamps(words, segment)

        # Chunk words into subtitle blocks
        for i in range(0, len(words), max_total):
            chunk = words[i : i + max_total]
            if not chunk:
                continue

            start = format_srt_time(chunk[0].get("start", 0))
            end   = format_srt_time(chunk[-1].get("end",   0))

            # Split chunk into lines
            lines = []
            for j in range(0, len(chunk), max_words):
                line_words = chunk[j : j + max_words]
                line = " ".join(
                    w.get("word", "").strip() for w in line_words
                )
                if line.strip():
                    lines.append(line)

            text = "\n".join(lines[:max_lines])
            if text.strip():
                srt_entries.append(
                    _make_srt_entry(index, start, end, text)
                )
                index += 1

    return "\n".join(srt_entries)


def _fill_missing_timestamps(
    words: list[dict],
    segment: dict,
) -> list[dict]:
    """
    Fill in missing word timestamps using neighbours or segment boundaries.

    WhisperX alignment occasionally leaves words without timestamps
    (score too low, silence, etc.). We patch these gaps so SRT
    entries always have valid start/end values.

    Strategy:
        - Missing start → use previous word's end (or segment start)
        - Missing end   → use next word's start   (or segment end)
    """
    seg_start = segment.get("start", 0.0)
    seg_end   = segment.get("end",   0.0)

    filled = []
    for i, word in enumerate(words):
        w = dict(word)  # shallow copy — don't mutate original

        # Fill missing start
        if w.get("start") is None:
            if filled:
                w["start"] = filled[-1].get("end", seg_start)
            else:
                w["start"] = seg_start

        # Fill missing end
        if w.get("end") is None:
            # Look ahead for next word with a start time
            next_start = None
            for j in range(i + 1, len(words)):
                if words[j].get("start") is not None:
                    next_start = words[j]["start"]
                    break
            w["end"] = next_start if next_start is not None else seg_end

        filled.append(w)

    return filled


def _safe_time(value) -> str:
    """Convert seconds value to SRT timecode safely."""
    try:
        return format_srt_time(float(value))
    except (TypeError, ValueError):
        return format_srt_time(0.0)


def _make_srt_entry(index: int, start: str, end: str, text: str) -> str:
    """Format a single SRT block."""
    return f"{index}\n{start} --> {end}\n{text}\n"


def format_srt_time(seconds: float) -> str:
    """
    Format seconds to SRT timecode: HH:MM:SS,mmm

    Args:
        seconds: float, e.g. 73.456

    Returns:
        "00:01:13,456"
    """
    seconds  = max(0.0, float(seconds))
    hours    = int(seconds // 3600)
    minutes  = int((seconds % 3600) // 60)
    secs     = int(seconds % 60)
    millis   = round((seconds % 1) * 1000)

    # Handle millisecond rounding overflow
    if millis >= 1000:
        millis -= 1000
        secs   += 1
    if secs >= 60:
        secs    -= 60
        minutes += 1
    if minutes >= 60:
        minutes -= 60
        hours   += 1

    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

# ============================================================================
# @block LOCAL:TRANSLATE:001 @desc Argos translation
# ============================================================================

def get_argos_installed_languages() -> list[str]:
    """Get list of installed Argos translation pairs e.g. ['en→ru', 'ru→en']"""
    try:
        import argostranslate.translate
        installed = argostranslate.translate.get_installed_languages()
        pairs = []
        for lang in installed:
            for t in lang.translations_from:
                pairs.append(f"{lang.code}→{t.to_language.code}")
        return pairs
    except Exception:
        return []


def install_argos_language(lang_code: str) -> bool:
    """
    Install Argos translation packages for en↔lang_code pair.
    Downloads both directions: en→lang and lang→en.

    Returns True if at least one package was installed.
    """
    try:
        import argostranslate.package
        import argostranslate.translate

        print("\n  Updating package index...")
        argostranslate.package.update_package_index()
        available = argostranslate.package.get_available_packages()

        installed_count = 0

        for from_code, to_code in [("en", lang_code), (lang_code, "en")]:
            for pkg in available:
                if pkg.from_code == from_code and pkg.to_code == to_code:
                    print(f"  Installing {from_code}→{to_code}...")
                    argostranslate.package.install_from_path(pkg.download())
                    installed_count += 1
                    break

        if installed_count > 0:
            log.info(
                f"Language '{lang_code}' installed ✓ "
                f"({installed_count} package(s))"
            )
            return True

        log.warning(f"No packages found for language code '{lang_code}'")
        return False

    except Exception as e:
        log.error(f"Argos language install error: {e}")
        return False


def list_available_argos_languages() -> list[str]:
    """
    Fetch available Argos language codes from package index.
    Returns sorted list of target language codes (from English).
    """
    try:
        import argostranslate.package
        argostranslate.package.update_package_index()
        available = argostranslate.package.get_available_packages()
        langs = {
            pkg.to_code
            for pkg in available
            if pkg.from_code == "en"
        }
        return sorted(langs)
    except Exception as e:
        log.error(f"Error fetching available languages: {e}")
        return []


def translate_srt(
    srt_content: str,
    source_lang: str,
    target_lang: str,
) -> str:
    """
    Translate SRT subtitle content using Argos Translate.

    Parses SRT structure, translates only text lines,
    preserves index numbers and timecodes exactly.

    Pivot translation:
        If no direct source→target pair exists and neither
        language is English, attempts source→en→target.

    Args:
        srt_content:  SRT string to translate
        source_lang:  ISO 639-1 source language code
        target_lang:  ISO 639-1 target language code

    Returns:
        Translated SRT string, or original on any failure.
    """
    # No-op cases
    if not target_lang:
        return srt_content
    if target_lang in ("orig", source_lang):
        return srt_content

    try:
        import argostranslate.translate
    except ImportError:
        log.warning("argostranslate not installed — skipping translation")
        return srt_content

    # Find translation object
    translation = _find_translation(source_lang, target_lang)

    # Pivot via English if no direct path
    if translation is None and source_lang != "en" and target_lang != "en":
        log.info(
            f"No direct {source_lang}→{target_lang} pair. "
            f"Trying pivot: {source_lang}→en→{target_lang}..."
        )
        srt_en = translate_srt(srt_content, source_lang, "en")
        if srt_en != srt_content:
            return translate_srt(srt_en, "en", target_lang)
        log.warning("Pivot translation failed — returning original")
        return srt_content

    if translation is None:
        log.warning(
            f"No translation pair: {source_lang}→{target_lang}\n"
            f"  Install: python subtitler_local.py --install-lang {target_lang}"
        )
        return srt_content

    log.info(f"Translating: {source_lang} → {target_lang}")
    return _translate_srt_lines(srt_content, translation)


def _find_translation(source_lang: str, target_lang: str):
    """
    Find installed Argos translation object for source→target.
    Returns translation object or None.
    """
    try:
        import argostranslate.translate
        installed = argostranslate.translate.get_installed_languages()
        for lang in installed:
            if lang.code == source_lang:
                for t in lang.translations_from:
                    if t.to_language.code == target_lang:
                        return t
    except Exception:
        pass
    return None


def _translate_srt_lines(srt_content: str, translation) -> str:
    """
    Walk through SRT lines and translate only subtitle text blocks.
    Preserves index numbers, timecodes, and empty separator lines.
    """
    lines            = srt_content.split("\n")
    translated_lines = []
    i                = 0

    while i < len(lines):
        line = lines[i]

        # SRT block: starts with an index number
        if line.strip().isdigit():
            # 1. Index line
            translated_lines.append(line)
            i += 1

            # 2. Timecode line
            if i < len(lines):
                translated_lines.append(lines[i])
                i += 1

            # 3. Text lines (one or more until empty line)
            text_parts = []
            while i < len(lines) and lines[i].strip():
                text_parts.append(lines[i].strip())
                i += 1

            if text_parts:
                original_text = " ".join(text_parts)
                try:
                    translated_text = translation.translate(original_text)
                    translated_lines.append(translated_text)
                except Exception as e:
                    log.warning(f"Translation error on block: {e}")
                    translated_lines.append(original_text)

            # 4. Empty separator line
            translated_lines.append("")

        else:
            translated_lines.append(line)

        i += 1

    return "\n".join(translated_lines)


# ============================================================================
# @block LOCAL:CONVERT:001 @desc SRT format converters
# ============================================================================

def srt_to_vtt(srt_content: str) -> str:
    """
    Convert SRT to WebVTT format.
    Only difference: header + comma→dot in timecodes.
    """
    return "WEBVTT\n\n" + srt_content.replace(",", ".")


def srt_to_txt(srt_content: str) -> str:
    """
    Extract plain text from SRT — strips index numbers and timecodes.
    Returns one subtitle text block per line.
    """
    lines      = srt_content.split("\n")
    text_lines = []
    i          = 0

    while i < len(lines):
        line = lines[i].strip()

        if line.isdigit():
            i += 1   # skip index
            if i < len(lines):
                i += 1   # skip timecode
            while i < len(lines) and lines[i].strip():
                text_lines.append(lines[i].strip())
                i += 1
        i += 1

    return "\n".join(text_lines)


# ============================================================================
# @block LOCAL:TASK:001 @desc Background task processing
# ============================================================================

def process_task(task_id: str, model_name: str, device: str) -> None:
    """
    Process a transcription task in a background thread.

    Pipeline:
        1. Get media duration (ffprobe)
        2. Transcribe + align (whisperx)
        3. Translate if requested (argostranslate)
        4. Store result in tasks dict
        5. Cleanup temp file

    Args:
        task_id:    unique task identifier
        model_name: whisper model to use
        device:     compute device ("cuda" | "mps" | "cpu")
    """
    with tasks_lock:
        task = tasks.get(task_id)
        if not task:
            return
        task["status"] = "processing"

    try:
        file_path       = task["file_path"]
        format_type     = task["format"] or "standard"
        target_language = task["target_language"]

        # Step 1 — duration
        duration = get_media_duration(file_path)
        with tasks_lock:
            task["duration"] = duration

        log.info(
            f"Task {task_id}: "
            f"duration={duration:.0f}s "
            f"format={format_type} "
            f"target={target_language or 'orig'} "
            f"device={device}"
        )

        # Step 2 — transcribe + align
        srt_content, detected_lang = transcribe(
            file_path,
            model_name=model_name,
            format_type=format_type,
            device=device,
        )

        with tasks_lock:
            task["source_language"] = detected_lang
            task["token_cost"]      = max(1, int(duration / 60 + 0.99))

        # Step 3 — translate (optional)
        if (
            target_language
            and target_language != "orig"
            and target_language != detected_lang
        ):
            log.info(
                f"Task {task_id}: "
                f"translating {detected_lang} → {target_language}"
            )
            srt_content = translate_srt(srt_content, detected_lang, target_language)

            with tasks_lock:
                task["translation_cost"] = max(1, int(duration / 180 + 0.99))

        # Step 4 — store result
        with tasks_lock:
            task["srt_content"]  = srt_content
            task["status"]       = "completed"
            task["completed_at"] = datetime.now().isoformat()

        log.info(f"Task {task_id}: completed ✓")

    except Exception as e:
        log.error(f"Task {task_id} failed: {e}", exc_info=True)
        with tasks_lock:
            task["status"] = "error"
            task["error"]  = str(e)

    finally:
        # Always cleanup temp file
        try:
            fp = tasks.get(task_id, {}).get("file_path", "")
            if fp and os.path.exists(fp):
                os.remove(fp)
        except Exception as e:
            log.warning(f"Temp file cleanup failed: {e}")


# ============================================================================
# @block LOCAL:API:001 @desc FastAPI application
# ============================================================================

def create_app(model_name: str, device: str) -> "fastapi.FastAPI":
    """
    Create and configure the FastAPI application.

    Endpoints mirror subtitler.online API for AE plugin compatibility:
        POST /api_upload.php    — upload file, start task
        GET  /api_status.php   — poll task status
        GET  /api_download.php — download result (srt/vtt/txt)
        GET  /api_test.php     — connection test + server info

    Args:
        model_name: whisper model name fixed for this server session
        device:     compute device fixed for this server session
    """
    from fastapi import FastAPI, File, UploadFile, Form, Query
    from fastapi.responses import PlainTextResponse, JSONResponse

    app = FastAPI(
        title="Subtitler Local",
        version=SCRIPT_VERSION,
        description="Self-hosted WhisperX transcription server",
    )

    # ----------------------------------------------------------------
    @app.post("/api_upload.php")
    async def upload_file(
        file: UploadFile = File(...),
        format: str = Form("standard"),
        target_language: str = Form(None),
    ):
        """
        Accept media file upload and start background transcription task.

        Form fields:
            file:            media file (any ffmpeg-readable format)
            format:          "standard" | "short" | "word"
            target_language: ISO 639-1 code or "orig" / empty for no translation

        Returns JSON with task_id for status polling.
        """
        ext       = Path(file.filename).suffix or ".tmp"
        task_id   = "local_" + uuid.uuid4().hex[:12]
        temp_path = TEMP_DIR / f"{task_id}{ext}"

        # Save uploaded file
        try:
            content = await file.read()
            temp_path.write_bytes(content)
        except Exception as e:
            log.error(f"Upload failed: {e}")
            return JSONResponse(
                {"error": "File upload failed", "detail": str(e)},
                status_code=500,
            )

        log.info(
            f"Upload: {file.filename} "
            f"({len(content):,} bytes) → {task_id}"
        )

        # Normalize target_language
        if target_language in (None, "", "orig", "null", "undefined"):
            target_language = None

        # Validate format
        if format not in FORMAT_SETTINGS:
            format = "standard"

        # Register task
        with tasks_lock:
            tasks[task_id] = {
                "task_id":          task_id,
                "filename":         file.filename,
                "format":           format,
                "target_language":  target_language,
                "file_path":        str(temp_path),
                "status":           "queued",
                "srt_content":      None,
                "source_language":  None,
                "token_cost":       0,
                "translation_cost": 0,
                "duration":         0,
                "error":            None,
                "created_at":       datetime.now().isoformat(),
                "completed_at":     None,
            }

        # Start background thread
        thread = threading.Thread(
            target=process_task,
            args=(task_id, model_name, device),
            daemon=True,
        )
        thread.start()

        return JSONResponse({
            "task_id":          task_id,
            "status":           "queued",
            "type":             "file",
            "token_cost":       0,
            "needs_translation": target_language is not None,
        })

    # ----------------------------------------------------------------
    @app.get("/api_status.php")
    async def task_status(task_id: str = Query(...)):
        """
        Poll task processing status.

        Query params:
            task_id: task identifier from /api_upload.php response

        Returns JSON with current status and metadata.
        Status values: "queued" | "processing" | "completed" | "error"
        """
        with tasks_lock:
            task = tasks.get(task_id)

        if not task:
            return JSONResponse(
                {"status": "error", "message": "Task not found"},
                status_code=404,
            )

        return JSONResponse({
            "task_uuid":        task["task_id"],
            "filename":         task["filename"],
            "status":           task["status"],
            "type":             "file",
            "token_cost":       task["token_cost"],
            "translation_cost": task["translation_cost"],
            "target_language":  task["target_language"],
            "source_language":  task["source_language"],
            "error":            task["error"],
            "created_at":       task["created_at"],
            "completed_at":     task["completed_at"],
        })

    # ----------------------------------------------------------------
    @app.get("/api_download.php")
    async def download_result(
        task_id: str = Query(...),
        format:  str = Query("srt"),
    ):
        """
        Download completed transcription result.

        Query params:
            task_id: task identifier
            format:  "srt" (default) | "vtt" | "txt"

        Returns plain text file with Content-Disposition header.
        """
        with tasks_lock:
            task = tasks.get(task_id)

        if not task:
            return JSONResponse(
                {"error": "Task not found"},
                status_code=404,
            )
        if task["status"] == "error":
            return JSONResponse(
                {"error": "Task failed", "detail": task.get("error")},
                status_code=500,
            )
        if task["status"] != "completed":
            return JSONResponse(
                {"error": f"Task not completed (status: {task['status']})"},
                status_code=400,
            )

        srt_content = task["srt_content"] or ""

        if format == "vtt":
            content  = srt_to_vtt(srt_content)
            filename = f"{task_id}.vtt"
        elif format == "txt":
            content  = srt_to_txt(srt_content)
            filename = f"{task_id}.txt"
        else:
            content  = srt_content
            filename = f"{task_id}.srt"

        return PlainTextResponse(
            content,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )

    # ----------------------------------------------------------------
    @app.get("/api_test.php")
    async def test_connection():
        """
        Connection test endpoint — used by AE plugin on setup.
        Returns server info, installed models and languages.
        """
        return JSONResponse({
            "status":              "ok",
            "server":              "Subtitler Local",
            "version":             SCRIPT_VERSION,
            "model":               model_name,
            "device":              device,
            "device_name":         device_display_name(device),
            "installed_models":    get_installed_whisper_models(),
            "installed_languages": get_argos_installed_languages(),
            "alignment_languages": sorted(WHISPERX_ALIGNMENT_LANGUAGES),
            "auth":                True,
            "balance":             999999,
        })

    return app

# ============================================================================
# @block LOCAL:MAIN:001 @desc CLI entry point
# ============================================================================

def main() -> None:
    """
    CLI entry point for Subtitler Local.

    Modes:
        --setup              Interactive setup wizard
        --list-models        Show installed Whisper models
        --install-lang CODE  Install Argos language pair
        --list-langs         List available/installed translation languages
        (default)            Start transcription server
    """
    parser = argparse.ArgumentParser(
        description=(
            f"Subtitler Local v{SCRIPT_VERSION} — "
            f"Self-hosted WhisperX transcription server"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python subtitler_local.py --setup
  python subtitler_local.py
  python subtitler_local.py --model large-v3
  python subtitler_local.py --model medium --port 9000
  python subtitler_local.py --list-models
  python subtitler_local.py --install-lang ru
  python subtitler_local.py --list-langs
        """,
    )

    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run interactive setup wizard",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Server port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        choices=WHISPER_MODELS,
        help=f"Whisper model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List installed Whisper models and exit",
    )
    parser.add_argument(
        "--install-lang",
        type=str,
        metavar="CODE",
        help="Install Argos translation language pair (e.g. 'ru', 'es')",
    )
    parser.add_argument(
        "--list-langs",
        action="store_true",
        help="List installed and available Argos languages and exit",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check installation status and exit",
    )

    args = parser.parse_args()

    # ================================================================
    # Mode: --setup
    # ================================================================
    if args.setup:
        run_setup()
        return

    # ================================================================
    # Mode: --check
    # ================================================================
    if args.check:
        print("=" * 60)
        print(f"  Subtitler Local v{SCRIPT_VERSION} — Installation Check")
        print("=" * 60)
        status = check_installation()
        print_installation_status(status)

        if is_fully_installed(status):
            print("  ✓ All required dependencies satisfied.")
            print(f"\n  Start server:")
            print(f"    python subtitler_local.py")
            if IS_WINDOWS:
                print(f"    Subtitler_Local.bat")
            else:
                print(f"    bash subtitler_local.sh")
            print("=" * 60)
            sys.exit(0)   # ← exit 0 = success → bat/sh продолжает    
        else:
            print("  ✗ Missing dependencies detected.")
            print(f"\n  Run setup:")
            print(f"    python subtitler_local.py --setup")
            print("=" * 60)
            sys.exit(1)   # ← exit 1 = failure → bat/sh запускает setup

    # ================================================================
    # Mode: --list-models
    # ================================================================
    if args.list_models:
        print("=" * 60)
        print(f"  Subtitler Local v{SCRIPT_VERSION} — Whisper Models")
        print("=" * 60)
        print_models_table(show_alignment=False)
        print(
            f"\n  Download a model:\n"
            f"    python subtitler_local.py --setup"
        )
        print("=" * 60)
        return

    # ================================================================
    # Mode: --install-lang
    # ================================================================
    if args.install_lang:
        if not check_argos():
            print(
                "  ✗ argostranslate is not installed.\n"
                f"    Run: {sys.executable} -m pip install argostranslate"
            )
            sys.exit(1)
        lang = args.install_lang.strip().lower()
        success = install_argos_language(lang)
        if success:
            pairs = get_argos_installed_languages()
            print(f"\n  Installed pairs: {', '.join(pairs)}")
        sys.exit(0 if success else 1)

    # ================================================================
    # Mode: --list-langs
    # ================================================================
    if args.list_langs:
        print("=" * 60)
        print(f"  Subtitler Local v{SCRIPT_VERSION} — Translation Languages")
        print("=" * 60)

        print("\n  Installed translation pairs:")
        pairs = get_argos_installed_languages()
        if pairs:
            for pair in pairs:
                print(f"    {pair}")
        else:
            print("    none")

        print("\n  Available for download (via --install-lang):")
        if check_argos():
            available = list_available_argos_languages()
            if available:
                # Print in columns of 8
                cols  = 8
                rows  = [available[i:i+cols] for i in range(0, len(available), cols)]
                for row in rows:
                    print("    " + "  ".join(f"{c:<6}" for c in row))
            else:
                print("    (could not fetch package index)")
        else:
            print(
                "    argostranslate not installed.\n"
                f"    Run: {sys.executable} -m pip install argostranslate"
            )

        print(
            f"\n  Install language:\n"
            f"    python subtitler_local.py --install-lang <code>"
        )
        print("=" * 60)
        return

    # ================================================================
    # Mode: start server (default)
    # ================================================================
    print("=" * 60)
    print(f"  Subtitler Local v{SCRIPT_VERSION}")
    print(f"  Platform: {PLATFORM}"
          f"{' (Apple Silicon)' if IS_APPLE_SILICON else ''}")
    print("=" * 60)

    # --- Preflight checks ---
    if not run_preflight():
        print(
            "\n  ✗ Missing required dependencies.\n"
            "  Run setup wizard:\n"
            "    python subtitler_local.py --setup"
        )
        sys.exit(1)

    # --- Detect device ---
    device = detect_device()
    log.info(f"Using device: {device_display_name(device)}")

    # --- Ensure model is available ---
    installed_models = get_installed_whisper_models()
    if args.model not in installed_models:
        if installed_models:
            # Default model not installed — use best available
            # "Best" = last in WHISPER_MODELS order (largest/most accurate)
            best = installed_models[-1]
            log.info(
                f"Model '{args.model}' not found in cache. "
                f"Using best available: '{best}'"
            )
            args.model = best
        else:
            # No models at all — download the requested one
            log.info(
                f"Model '{args.model}' not found in cache. "
                f"Downloading..."
            )
            if not download_whisper_model(args.model, device="cpu"):
                print(
                    f"\n  ✗ Failed to download model '{args.model}'.\n"
                    f"  Check internet connection or choose another model:\n"
                    f"    python subtitler_local.py --list-models"
                )
                sys.exit(1)

    # --- argostranslate status ---
    if not check_argos():
        log.warning(
            "argostranslate not installed — translation unavailable.\n"
            f"  Install: {sys.executable} -m pip install argostranslate"
        )

    # --- Create and start server ---
    try:
        import uvicorn
    except ImportError:
        print(
            "  ✗ uvicorn not found.\n"
            f"  Run: {sys.executable} -m pip install uvicorn[standard]"
        )
        sys.exit(1)

    app = create_app(model_name=args.model, device=device)

    # Server startup banner
    print()
    print(f"  Model  : {args.model}")
    print(f"  Device : {device_display_name(device)}")
    print(f"  Server : http://localhost:{args.port}")
    print()
    print(f"  After Effects plugin settings:")
    print(f"    Server URL : http://localhost:{args.port}")
    print(f"    Mode       : Direct")
    print(f"    API Key    : local")
    print()
    print(f"  Press Ctrl+C to stop")
    print("=" * 60)
    print()

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=args.port,
        log_level="warning",   # suppress uvicorn INFO spam, use our logger
    )


# ============================================================================
# @block LOCAL:MAIN:002 @desc Script entry guard
# ============================================================================

if __name__ == "__main__":
    main()                        