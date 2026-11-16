#!/usr/bin/env bash
# ============================================================
#  Subtitler Local v2.0.0 — macOS / Linux launcher
#
#  Usage:
#    bash subtitler_local.sh              Start server
#    bash subtitler_local.sh --setup      Run setup wizard
#    bash subtitler_local.sh --model medium
#    bash subtitler_local.sh --port 9000
#    bash subtitler_local.sh --check      Check installation
#
#  Make executable (once):
#    chmod +x subtitler_local.sh
#  Then run directly:
#    ./subtitler_local.sh
# ============================================================

set -euo pipefail

# ============================================================
# Constants
# ============================================================

SCRIPT_VERSION="2.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/subtitler_local.py"

# Terminal colors (disabled if not a TTY)
if [ -t 1 ]; then
    RED='\033[0;31m'
    YELLOW='\033[1;33m'
    GREEN='\033[0;32m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    RESET='\033[0m'
else
    RED='' YELLOW='' GREEN='' CYAN='' BOLD='' RESET=''
fi

# ============================================================
# Helpers
# ============================================================

print_header() {
    echo "============================================================"
    echo "  Subtitler Local v${SCRIPT_VERSION}"
    echo "  Self-hosted WhisperX transcription server"
    echo "============================================================"
    echo
}

print_error() {
    echo -e "${RED}  [ERROR] $1${RESET}" >&2
}

print_warn() {
    echo -e "${YELLOW}  [!] $1${RESET}"
}

print_ok() {
    echo -e "${GREEN}  [✓] $1${RESET}"
}

print_info() {
    echo -e "${CYAN}  $1${RESET}"
}

# ============================================================
# STEP 1 — Detect platform
# ============================================================

detect_platform() {
    OS="$(uname -s)"
    ARCH="$(uname -m)"

    case "$OS" in
        Darwin)
            PLATFORM="macOS"
            if [ "$ARCH" = "arm64" ]; then
                PLATFORM_DETAIL="macOS (Apple Silicon)"
            else
                PLATFORM_DETAIL="macOS (Intel)"
            fi
            ;;
        Linux)
            PLATFORM="Linux"
            PLATFORM_DETAIL="Linux ($ARCH)"
            ;;
        *)
            PLATFORM="Unknown"
            PLATFORM_DETAIL="$OS $ARCH"
            ;;
    esac

    echo "  Platform: ${PLATFORM_DETAIL}"
    echo
}

# ============================================================
# STEP 2 — Locate Python 3.9+
# ============================================================

find_python() {
    PYTHON_CMD=""

    # Candidates in preference order
    local candidates=(
        "python3.12"
        "python3.11"
        "python3.10"
        "python3.9"
        "python3"
        "python"
    )

    # Also check Homebrew prefix on macOS
    if [ "$PLATFORM" = "macOS" ]; then
        # Apple Silicon Homebrew
        if [ -x "/opt/homebrew/bin/python3" ]; then
            candidates=("/opt/homebrew/bin/python3" "${candidates[@]}")
        fi
        # Intel Homebrew
        if [ -x "/usr/local/bin/python3" ]; then
            candidates=("/usr/local/bin/python3" "${candidates[@]}")
        fi
    fi

    for candidate in "${candidates[@]}"; do
        if command -v "$candidate" >/dev/null 2>&1; then
            # Verify version >= 3.9
            local version
            version=$("$candidate" -c \
                "import sys; print(sys.version_info >= (3,9))" 2>/dev/null \
                || echo "False")

            if [ "$version" = "True" ]; then
                PYTHON_CMD="$candidate"
                local ver_str
                ver_str=$("$candidate" --version 2>&1)
                print_ok "Python: $ver_str ($PYTHON_CMD)"
                return 0
            fi
        fi
    done

    return 1
}

# ============================================================
# STEP 3 — Check ffmpeg (macOS/Linux guidance)
# ============================================================

check_ffmpeg_sh() {
    if command -v ffmpeg >/dev/null 2>&1; then
        local ver
        ver=$(ffmpeg -version 2>&1 | head -1)
        print_ok "ffmpeg: $ver"
        return 0
    fi

    print_warn "ffmpeg not found."
    echo

    if [ "$PLATFORM" = "macOS" ]; then
        echo "  Install via Homebrew:"
        echo "    brew install ffmpeg"
        echo
        echo "  No Homebrew? https://brew.sh"
    else
        echo "  Install via package manager:"
        echo "    Ubuntu/Debian : sudo apt install ffmpeg"
        echo "    Fedora        : sudo dnf install ffmpeg"
        echo "    Arch          : sudo pacman -S ffmpeg"
    fi

    echo
    echo "  After installing ffmpeg, re-run this script."
    echo
    return 1
}

# ============================================================
# STEP 4 — Main logic
# ============================================================

main() {
    print_header
    detect_platform

    # --- Locate Python ---
    echo "  Locating Python..."
    echo
    if ! find_python; then
        print_error "Python 3.9+ not found."
        echo
        if [ "$PLATFORM" = "macOS" ]; then
            echo "  Install via Homebrew:"
            echo "    brew install python@3.12"
            echo
            echo "  Or download: https://www.python.org/downloads/"
        else
            echo "  Install via package manager:"
            echo "    Ubuntu/Debian : sudo apt install python3.12"
            echo "    Fedora        : sudo dnf install python3.12"
            echo
            echo "  Or download: https://www.python.org/downloads/"
        fi
        echo
        exit 1
    fi

    echo

    # --- Verify script exists ---
    if [ ! -f "$PYTHON_SCRIPT" ]; then
        print_error "subtitler_local.py not found."
        echo "  Expected: $PYTHON_SCRIPT"
        echo "  Make sure subtitler_local.sh is in the same"
        echo "  directory as subtitler_local.py"
        echo
        exit 1
    fi

    # --- Handle --setup flag ---
    if [[ "${1:-}" == "--setup" ]]; then
        echo "  Running setup wizard..."
        echo
        "$PYTHON_CMD" "$PYTHON_SCRIPT" --setup
        echo
        print_ok "Setup finished."
        exit 0
    fi

    # --- Check ffmpeg early (before python check) ---
    echo "  Checking ffmpeg..."
    if ! check_ffmpeg_sh; then
        exit 1
    fi

    # --- Check installation via --check ---
    echo "  Checking installation..."
    echo

    if ! "$PYTHON_CMD" "$PYTHON_SCRIPT" --check >/dev/null 2>&1; then
        print_warn "Some dependencies are missing."
        echo
        echo "  Running setup wizard..."
        echo

        sleep 2

        "$PYTHON_CMD" "$PYTHON_SCRIPT" --setup

        # Re-check after setup
        echo
        echo "  Re-checking installation..."
        if ! "$PYTHON_CMD" "$PYTHON_SCRIPT" --check >/dev/null 2>&1; then
            print_error "Setup did not complete successfully."
            echo "  Please re-run:"
            echo "    bash subtitler_local.sh --setup"
            echo
            exit 1
        fi
    fi

    print_ok "All dependencies satisfied."
    echo

    # --- Start server ---
    echo "  Starting server..."
    echo "  Press Ctrl+C to stop."
    echo

    # Pass all arguments through to Python script
    # Use 'exec' to replace shell process with Python
    # (cleaner Ctrl+C handling)
    exec "$PYTHON_CMD" "$PYTHON_SCRIPT" "$@"
}

# ============================================================
# STEP 5 — Trap Ctrl+C gracefully
# ============================================================

cleanup() {
    echo
    echo
    print_info "Server stopped."
    exit 0
}

trap cleanup INT TERM

# ============================================================
# Entry point
# ============================================================

main "$@"