"""Switch which fine-tuned model the local vLLM server is running. HOME / LOCALHOST USE ONLY.

    python -m app.serving list | status | switch <key> | stop      (or scripts/switch_model.sh)

Safety: this starts and kills processes on this machine, so it only ever acts on a vLLM server at
127.0.0.1/localhost, and the web page only exposes it when VIETPOET_ALLOW_SWITCH=1 and the request comes
from a private (home-network) address with no proxy headers (see is_home_request).
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = Path(os.environ.get("VIETPOET_MODELS_DIR", Path.home() / "vietpoet-models"))
BASE_URL = os.environ.get("VIETPOET_BASE_URL", "http://127.0.0.1:8000/v1")
LOG = ROOT / "run" / "vllm.log"

_MM_OFF = '{"image":0,"audio":0}'
MODELS: dict[str, dict] = {
    "4b": {"label": "Qwen3.5-4B (fastest)", "path": MODELS_DIR / "sft-v1" / "merged", "family": "qwen",
           "util": "0.85", "args": [], "minutes": "about 1"},
    "9b": {"label": "Qwen3.5-9B", "path": MODELS_DIR / "sft-9b-v1" / "merged", "family": "qwen",
           "util": "0.90", "args": ["--max-num-batched-tokens", "1024", "--max-num-seqs", "32"], "minutes": "1-2"},
    "gemma": {"label": "Gemma 4 12B (FP8)", "path": MODELS_DIR / "sft-gemma4-12b-v1" / "merged", "family": "gemma",
              "util": "0.90", "args": ["--quantization", "fp8", "--max-num-batched-tokens", "2560",
                                       "--max-num-seqs", "32", "--limit-mm-per-prompt", _MM_OFF], "minutes": "about 2"},
}
_PROXY_HEADERS = {"x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "x-real-ip", "forwarded",
                  "cf-connecting-ip", "true-client-ip", "via"}
_HOME_NETWORKS = [ipaddress.ip_network(n) for n in (
    "127.0.0.0/8", "::1/128",                      # this machine
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",   # RFC 1918 home / office LANs
    "169.254.0.0/16", "fe80::/10",                 # link-local
    "fc00::/7")]                                   # IPv6 unique-local
_lock = threading.Lock()


def available() -> dict[str, dict]:
    return {k: m for k, m in MODELS.items() if Path(m["path"]).is_dir()}


def is_home_request(client_host: str | None, headers: dict | None = None) -> bool:
    """True only for loopback / private-network clients that did not come through a proxy or tunnel."""
    if any(str(h).lower() in _PROXY_HEADERS for h in (headers or {})):
        return False
    try:
        ip = ipaddress.ip_address((client_host or "").strip())
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return any(ip in net for net in _HOME_NETWORKS)


def is_local_server() -> bool:
    return (urlparse(BASE_URL).hostname or "") in ("127.0.0.1", "localhost", "::1")


def is_switching() -> bool:
    return _lock.locked()


def _models_response() -> dict | None:
    try:
        with urllib.request.urlopen(BASE_URL.rstrip("/") + "/models", timeout=2) as r:
            return json.load(r)
    except (urllib.error.URLError, OSError, ValueError):
        return None


def current_key() -> str | None:
    """Registry key of the model the server is running, 'other' if unknown, None if no server."""
    data = _models_response()
    if not data or not data.get("data"):
        return None
    root = os.path.realpath(str(data["data"][0].get("root") or ""))
    for key, m in MODELS.items():
        if os.path.realpath(str(m["path"])) == root:
            return key
    return "other"


def _vllm_pids() -> list[int]:
    me, pids = os.getpid(), []
    for d in os.listdir("/proc"):
        if not d.isdigit() or int(d) == me:
            continue
        try:
            cmd = Path(f"/proc/{d}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="ignore")
        except OSError:
            continue
        if re.search(r"(^|[/ ])vllm serve\b", cmd) or cmd.startswith("VLLM::"):
            pids.append(int(d))
    return pids


def _gpu_used_mib() -> int | None:
    exe = shutil.which("nvidia-smi") or ("/run/host/usr/bin/nvidia-smi" if Path("/run/host/usr/bin/nvidia-smi").exists() else None)
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout.split()
        return int(out[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def stop_server(timeout: float = 45.0) -> None:
    for pid in _vllm_pids():
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    end = time.time() + timeout
    while time.time() < end and (_vllm_pids() or _models_response()):
        time.sleep(1)
    for pid in _vllm_pids():
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    end = time.time() + 30
    while time.time() < end:                      # wait for the GPU memory to be released
        used = _gpu_used_mib()
        if used is None or used < 3500:
            break
        time.sleep(1)
    time.sleep(2)


def _start(key: str) -> subprocess.Popen:
    m = MODELS[key]
    LOG.parent.mkdir(exist_ok=True)
    env = {**os.environ, "VLLM_GPU_UTIL": m["util"]}
    return subprocess.Popen(["bash", str(ROOT / "scripts" / "serve.sh"), str(m["path"]), *m["args"]],
                            env=env, cwd=ROOT, stdout=open(LOG, "ab"), stderr=subprocess.STDOUT, start_new_session=True)


def _log_tail(n: int = 6) -> str:
    try:
        lines = [l for l in LOG.read_text(errors="ignore").splitlines() if "import_utils" not in l]
        return " | ".join(l.strip()[-160:] for l in lines[-n:])
    except OSError:
        return ""


def switch(key: str, timeout: float = 420.0) -> Iterator[tuple[bool, str]]:
    """Stop the running server and start `key`. Yields (finished, message) progress updates."""
    if key not in available():
        raise ValueError(f"Unknown or missing model '{key}'. Available: {', '.join(available()) or 'none'}")
    if not is_local_server():
        raise RuntimeError("Refusing to switch: VIETPOET_BASE_URL is not a local vLLM server.")
    if not _lock.acquire(blocking=False):
        raise RuntimeError("A model switch is already in progress.")
    try:
        m = MODELS[key]
        if current_key() == key:
            yield True, f"{m['label']} is already running."
            return
        yield False, "Stopping the current model..."
        stop_server()
        proc, t0 = _start(key), time.time()
        yield False, f"Loading {m['label']}..."
        while True:
            if proc.poll() is not None:
                raise RuntimeError(f"vLLM exited while loading {m['label']}. Log: {_log_tail()}")
            if current_key() == key:
                yield True, f"{m['label']} is ready (took {int(time.time() - t0)} s)."
                return
            if time.time() - t0 > timeout:
                stop_server()
                raise TimeoutError(f"{m['label']} did not become ready within {int(timeout)} s. Log: {_log_tail()}")
            yield False, f"Loading {m['label']}... {int(time.time() - t0)} s"
            time.sleep(3)
    finally:
        _lock.release()


def stop() -> Iterator[tuple[bool, str]]:
    """Shut the local vLLM server down and free the GPU. Yields (finished, message) progress updates."""
    if not is_local_server():
        raise RuntimeError("Refusing to stop: VIETPOET_BASE_URL is not a local vLLM server.")
    if not _lock.acquire(blocking=False):
        raise RuntimeError("A model switch is in progress.")
    try:
        if current_key() is None and not _vllm_pids():
            yield True, "No model server is running."
            return
        yield False, "Shutting down the model server..."
        stop_server()
        yield True, "Model server stopped; the GPU is free."
    finally:
        _lock.release()


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "list":
        cur = current_key()
        for k, m in MODELS.items():
            state = "running" if k == cur else ("ready" if k in available() else "missing")
            print(f"{k:6} {state:8} {m['label']}  ({m['path']})")
    elif cmd == "status":
        print(current_key() or "no server running")
    elif cmd == "stop":
        for _, msg in stop():
            print(msg, flush=True)
    elif cmd == "switch" and len(argv) == 2:
        try:
            for done, msg in switch(argv[1]):
                print(msg, flush=True)
        except (ValueError, RuntimeError, TimeoutError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
