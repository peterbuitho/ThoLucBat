#!/bin/bash
# VietPoet launcher for Apple silicon Macs: choose a model, download it, start LM Studio's server, load the model,
# open the poem page. Written for the stock macOS bash 3.2 (no bash 4 features).
#   start.sh [--size 4B|9B] [--format mlx|gguf] [--reconfigure] [--no-browser] [--setup-only]
# Environment: VIETPOET_SIZE, VIETPOET_BITS (8|4), VIETPOET_FORMAT (mlx|gguf), VIETPOET_CANDIDATES, VIETPOET_PORT,
#              VIETPOET_MODELS_DIR (LM Studio's models folder, if the launcher cannot find it).

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OWNER="${VIETPOET_HF_OWNER:-peterbuitho}"
HF_BASE="${VIETPOET_HF_BASE:-https://huggingface.co}"
PAGE_PORT="${VIETPOET_PORT:-7860}"
IDENT=vietpoet
SETTINGS="$ROOT/settings.env"
PARALLEL=8              # requests at a time; LM Studio may ignore it for MLX models
USABLE_PCT=65           # macOS lets the graphics side wire roughly two thirds of the memory
RESERVE_MIB=1500        # kept free for macOS, the browser and the page itself

OPT_SIZE=""; OPT_FORMAT=""; OPT_RECONFIGURE=0; OPT_NO_BROWSER=0; OPT_SETUP_ONLY=0
LMS=""; PY=""; UV=""; PAGE_PID=""; LOADED=0

if [ -t 1 ]; then C_CYAN=$'\033[36m'; C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'; C_OFF=$'\033[0m'; else C_CYAN=""; C_YELLOW=""; C_RED=""; C_OFF=""; fi
step() { echo; echo "${C_CYAN}== $1${C_OFF}"; }
note() { echo "   $1"; }
warn() { echo "${C_YELLOW}$1${C_OFF}"; }
die() { echo; echo "${C_RED}Something went wrong: $1${C_OFF}"; exit 1; }
gb() { awk -v m="$1" 'BEGIN { printf "%.1f GB", m / 1024 }'; }

# Unified memory (MiB) the loaded model needs: the weights (MLX or GGUF file) plus about 1 GB for the cache and overhead.
# These are estimates from the file sizes, not measurements (the Windows launcher's numbers were measured).
need_mib() {   # size bits
    case "$1$2" in
        4B8) echo 5700;; 4B4) echo 3600;; 9B8) echo 10900;; 9B4) echo 6700;;
    esac
}

pick_bits() {  # size usable_mib -> the largest number of bits that fits, or nothing
    local b
    for b in 8 4; do
        if [ "$(need_mib "$1" "$b")" -le "$2" ]; then echo "$b"; return 0; fi
    done
    return 1
}

ram_mib() {
    if [ -n "${VIETPOET_TEST_RAM_MIB:-}" ]; then echo "$VIETPOET_TEST_RAM_MIB"; return; fi
    echo $(( $(sysctl -n hw.memsize) / 1048576 ))
}

ask() {        # question default option... -> the chosen number (Enter, or no keyboard, gives the default)
    local q="$1" def="$2" i=1 o ans="" n
    shift 2
    n=$#
    { echo; echo "$q"; for o in "$@"; do echo "  [$i] $o"; i=$((i + 1)); done; printf 'Type 1-%s and press Enter (just Enter = %s): ' "$n" "$def"; } >&2
    if [ -t 0 ]; then read -r ans || ans=""; else echo >&2; fi
    case "$ans" in
        ''|*[!0-9]*) echo "$def" ;;
        *) if [ "$ans" -ge 1 ] && [ "$ans" -le "$n" ]; then echo "$ans"; else echo "$def"; fi ;;
    esac
}

choose_setup() {   # sets SIZE and BITS
    local ram budget size n fit alt
    ram=$(ram_mib)
    budget=$(( ram * USABLE_PCT / 100 - RESERVE_MIB ))
    step "Checking this Mac"
    note "memory: $(gb "$ram") shared by processor and graphics; about $(gb "$budget") is usable for the model"

    size=$(echo "${VIETPOET_SIZE:-$OPT_SIZE}" | tr 'a-z' 'A-Z')
    if [ "$size" != 4B ] && [ "$size" != 9B ]; then
        n=$(ask "Which model do you want?" 1 \
            "4B - faster, smaller download (2.5 to 4.6 GB). Recommended." \
            "9B - larger (5.6 to 9.8 GB), needs more memory and is a little slower")
        if [ "$n" = 2 ]; then size=9B; else size=4B; fi
    fi

    fit=$(pick_bits "$size" "$budget")
    if [ -z "$fit" ]; then
        warn "The $size model needs about $(gb "$(need_mib "$size" 4)") of memory and only about $(gb "$budget") is free for it."
        alt=""
        if [ "$size" = 9B ]; then alt=$(pick_bits 4B "$budget"); fi
        if [ -n "$alt" ]; then
            n=$(ask "What now?" 1 "Use the 4B model instead. Recommended." "Try the 9B model anyway (may be very slow or fail to load)")
            if [ "$n" = 1 ]; then size=4B; fit=$alt; else fit=4; fi
        else
            warn "Close other programs and try again, or continue with the smallest setup (it may be slow or fail to load)."
            fit=4
        fi
    fi
    SIZE=$size; BITS=${VIETPOET_BITS:-$fit}
}

save_setup() { printf 'SIZE=%s\nBITS=%s\n' "$SIZE" "$BITS" > "$SETTINGS"; }

load_setup() {     # reads settings.env; returns 1 if it is missing or not valid
    [ -f "$SETTINGS" ] || return 1
    local s b
    s=$(sed -n 's/^SIZE=//p' "$SETTINGS" | head -n 1)
    b=$(sed -n 's/^BITS=//p' "$SETTINGS" | head -n 1)
    case "$s" in 4B|9B) ;; *) return 1 ;; esac
    case "$b" in 8|4) ;; *) return 1 ;; esac
    SIZE=$s; BITS=${VIETPOET_BITS:-$b}
}

find_lms() {
    if command -v lms >/dev/null 2>&1; then LMS=$(command -v lms)
    elif [ -x "$HOME/.lmstudio/bin/lms" ]; then LMS="$HOME/.lmstudio/bin/lms"
    fi
}

find_uv() {
    if command -v uv >/dev/null 2>&1; then UV=$(command -v uv)
    elif [ -x "$HOME/.local/bin/uv" ]; then UV="$HOME/.local/bin/uv"
    elif [ -x "$ROOT/tools/uv" ]; then UV="$ROOT/tools/uv"
    fi
}

setup_python() {   # uv brings its own Python, so nothing needs to be installed
    step "Preparing the poem page"
    find_uv
    if [ -z "$UV" ]; then
        note "downloading uv (a small Python installer, about 20 MB)"
        mkdir -p "$ROOT/tools"
        curl -fL --progress-bar "https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-apple-darwin.tar.gz" \
            | tar -xz -C "$ROOT/tools" --strip-components=1 || die "Could not download uv. Check your internet connection and run this again."
        UV="$ROOT/tools/uv"
        [ -x "$UV" ] || die "Could not unpack uv."
    fi
    local venv="$ROOT/.venv-app" marker want
    PY="$venv/bin/python"
    marker="$venv/requirements.sha256"
    want=$(shasum -a 256 "$ROOT/requirements.txt" | cut -d' ' -f1)
    if [ -x "$PY" ] && [ -f "$marker" ] && [ "$(cat "$marker")" = "$want" ]; then
        note "ready"
    else
        note "installing (first run only, a minute or two)"
        "$UV" venv "$venv" --python 3.12 --clear --quiet || die "Could not create the Python environment."
        "$UV" pip install --python "$PY" -r "$ROOT/requirements.txt" --quiet || die "Could not install the page requirements."
        echo "$want" > "$marker"
    fi
}

models_dir() {     # LM Studio's models folder
    if [ -n "${VIETPOET_MODELS_DIR:-}" ]; then echo "$VIETPOET_MODELS_DIR"; return; fi
    local d=""
    if [ -f "$HOME/.lmstudio/settings.json" ]; then
        d=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("downloadsFolder",""))' "$HOME/.lmstudio/settings.json" 2>/dev/null)
    fi
    echo "${d:-$HOME/.lmstudio/models}"
}

locate() {         # name -> LM Studio's key for the model whose path contains it, or nothing
    "$LMS" ls --json 2>/dev/null | "$PY" -c '
import sys, json
name = sys.argv[1]
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if isinstance(data, dict):
    data = data.get("models", [])
for m in data:
    if name in str(m.get("path", "")):
        print(m.get("modelKey") or m.get("path"))
        break
' "$1"
}

remote_exists() {  # a Hugging Face repo answers 200 when it is public and exists (401 or 404 when it does not)
    [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$HF_BASE/api/models/$1")" = 200 ]
}

set_names() {      # format -> REPO, NAME (what LM Studio's path contains), PATTERN (files to fetch, empty = all), SUBDIR
    case "$1" in
        mlx)
            NAME="VietPoet-Qwen3.5-$SIZE-MLX-${BITS}bit"
            REPO="$OWNER/$NAME"; PATTERN=""; SUBDIR="$OWNER/$NAME" ;;
        gguf)
            local q; if [ "$BITS" = 8 ]; then q=Q8_0; else q=Q4_K_M; fi
            NAME="VietPoet-Qwen3.5-$SIZE-$q.gguf"
            REPO="$OWNER/VietPoet-Qwen3.5-$SIZE-GGUF"; PATTERN="$NAME"; SUBDIR="$REPO" ;;
    esac
}

download_model() {
    local tmp="$ROOT/downloads/$(basename "$REPO")" dest
    dest="$(models_dir)/$SUBDIR"
    step "Downloading $NAME from Hugging Face ($REPO)"
    note "this is a few GB; if it stops, run this file again and it resumes"
    mkdir -p "$tmp"
    HF_HUB_DISABLE_TELEMETRY=1 HF_ENDPOINT="$HF_BASE" "$PY" - "$REPO" "$tmp" "$PATTERN" <<'PYEOF' || die "Download failed. Check your internet connection and run this again."
import sys
from huggingface_hub import snapshot_download
repo, dest, pattern = sys.argv[1:4]
snapshot_download(repo, local_dir=dest, allow_patterns=[pattern] if pattern else None)
PYEOF
    rm -rf "$tmp/.cache"
    note "adding it to LM Studio ($dest)"
    mkdir -p "$dest" && cp -R "$tmp"/. "$dest"/ || die "Could not copy the model into LM Studio's models folder."
    rm -rf "$tmp"
    rmdir "$ROOT/downloads" 2>/dev/null
}

resolve_model() {  # sets KEY, NAME, FORMAT_USED; tries MLX first, then the GGUF file
    local formats fmt i
    if [ -n "${VIETPOET_FORMAT:-$OPT_FORMAT}" ]; then formats="${VIETPOET_FORMAT:-$OPT_FORMAT}"; else formats="mlx gguf"; fi
    KEY=""
    for fmt in $formats; do
        set_names "$fmt"
        KEY=$(locate "$NAME")
        if [ -z "$KEY" ] && remote_exists "$REPO"; then
            download_model
            for i in 1 2 3 4 5; do
                KEY=$(locate "$NAME"); [ -n "$KEY" ] && break
                sleep 2
            done
            [ -n "$KEY" ] || die "The model was downloaded to $(models_dir)/$SUBDIR but LM Studio does not list it. If you moved LM Studio's models folder, set VIETPOET_MODELS_DIR to it."
        elif [ -z "$KEY" ]; then
            note "$REPO is not available (yet)"
        else
            note "already downloaded: $KEY"
        fi
        if [ -n "$KEY" ]; then FORMAT_USED=$fmt; return 0; fi
    done
    die "No model could be found or downloaded ($OWNER/VietPoet-Qwen3.5-$SIZE-...). Check your internet connection."
}

cleanup() {
    if [ -n "$PAGE_PID" ]; then kill "$PAGE_PID" 2>/dev/null; fi
    if [ "$LOADED" = 1 ]; then "$LMS" unload "$IDENT" >/dev/null 2>&1; fi     # free the memory
}

main() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --size) OPT_SIZE="${2:-}"; shift ;;
            --format) OPT_FORMAT="${2:-}"; shift ;;
            --reconfigure) OPT_RECONFIGURE=1 ;;
            --no-browser) OPT_NO_BROWSER=1 ;;
            --setup-only) OPT_SETUP_ONLY=1 ;;
            *) die "unknown option $1" ;;
        esac
        shift
    done
    cd "$ROOT" || exit 1
    trap cleanup EXIT
    trap 'exit 130' INT TERM HUP

    # ---- 1. This Mac and LM Studio's command line tool -----------------------------------------
    [ "$(uname -s)" = Darwin ] || die "This launcher is for Macs."
    [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = 1 ] || die "This needs a Mac with Apple silicon (M1 or newer)."
    step "Looking for LM Studio"
    find_lms
    [ -n "$LMS" ] || die "LM Studio was not found. Install it from https://lmstudio.ai, open it once, close it, then run this again."
    note "found $LMS"

    # ---- 2. Python (also used below to download the model) ---------------------------------------
    setup_python

    # ---- 3. Model size: ask on the first run, then remember ------------------------------------------
    if [ "$OPT_RECONFIGURE" = 1 ] || [ -n "${VIETPOET_SIZE:-$OPT_SIZE}" ] || ! load_setup; then
        # our own model from an earlier run would count against the memory we are about to look at
        if "$LMS" ps 2>&1 | grep -Eq "^[[:space:]]*$IDENT[[:space:]]"; then "$LMS" unload "$IDENT" >/dev/null 2>&1; sleep 2; fi
        choose_setup
        save_setup
        note 'saved; run "Change model or hardware.command" to choose again'
    fi
    local candidates="${VIETPOET_CANDIDATES:-$PARALLEL}"
    step "Model: $SIZE, $BITS-bit ($PARALLEL requests at a time, $candidates candidates per line)"

    # ---- 4. Get the model --------------------------------------------------------------------
    resolve_model
    note "using the $FORMAT_USED version"

    # ---- 5. Start the server and load the model ------------------------------------------------
    step "Starting the LM Studio server"
    local port=1234 status i ready=0
    status=$("$LMS" status 2>&1)
    if echo "$status" | grep -Eq 'Server:[[:space:]]*ON'; then
        port=$(echo "$status" | sed -nE 's/.*Server:[[:space:]]*ON.*port:[[:space:]]*([0-9]+).*/\1/p' | head -n 1)
        port=${port:-1234}
    else
        "$LMS" server start -p "$port" >/dev/null 2>&1
    fi
    local api="http://localhost:$port/v1"
    for i in $(seq 1 60); do
        if curl -s -o /dev/null --max-time 5 "$api/models"; then ready=1; break; fi
        sleep 1
    done
    [ "$ready" = 1 ] || die "The LM Studio server did not answer on $api."
    note "server ready on $api"

    step "Loading the model"
    if "$LMS" ps 2>&1 | grep -Eq "^[[:space:]]*$IDENT[[:space:]]"; then "$LMS" unload "$IDENT" >/dev/null 2>&1; fi
    local context=$(( 1024 * PARALLEL ))
    if "$LMS" load "$KEY" --identifier "$IDENT" -c "$context" --parallel "$PARALLEL" -y >/dev/null 2>&1; then
        LOADED=1
    elif "$LMS" load "$KEY" --identifier "$IDENT" -c "$context" -y >/dev/null 2>&1; then
        # this LM Studio version has no parallel setting for this model: requests run one after another, so ask for fewer
        LOADED=1
        note "no parallel requests for this model; using fewer candidates"
        [ -n "${VIETPOET_CANDIDATES:-}" ] || candidates=4
    else
        die "LM Studio could not load the model (not enough memory?). Run \"Change model or hardware.command\" and pick a smaller setup."
    fi
    note "loaded"

    [ "$OPT_SETUP_ONLY" = 1 ] && { step "Setup finished (--setup-only)."; return 0; }

    # ---- 6. Run the page -----------------------------------------------------------------------
    export VIETPOET_BASE_URL="$api" VIETPOET_MODEL="$IDENT" VIETPOET_CANDIDATES="$candidates" VIETPOET_PORT="$PAGE_PORT"
    export GRADIO_ANALYTICS_ENABLED=False PYTHONUTF8=1
    step "The poem page is starting on http://127.0.0.1:$PAGE_PORT  (close this window or press Ctrl+C to stop)"
    "$PY" -m app.webui &
    PAGE_PID=$!
    if [ "$OPT_NO_BROWSER" != 1 ]; then
        for i in $(seq 1 60); do
            kill -0 "$PAGE_PID" 2>/dev/null || break
            if curl -s -o /dev/null --max-time 5 "http://127.0.0.1:$PAGE_PORT/"; then open "http://127.0.0.1:$PAGE_PORT/"; break; fi
            sleep 1
        done
    fi
    wait "$PAGE_PID"
}

if [ "${VIETPOET_SOURCE_ONLY:-}" != 1 ]; then main "$@"; fi
