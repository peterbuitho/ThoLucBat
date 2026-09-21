"""Build the local-installation packages: dist/VietPoet-win.zip and dist/VietPoet-mac.zip (app + launcher, no models,
no private files).

    python scripts/build_package.py [--target win|mac|all] [--out dist]

Each zip holds only the page code, a launcher and a README. The launcher downloads the model from Hugging Face on
first run (GGUF on Windows, MLX on macOS) and sets up Python through uv, so the zip stays a few hundred KB.
"""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIN = ROOT / "packaging" / "windows"
MAC = ROOT / "packaging" / "mac"
APP_FILES = ["__init__.py", "agent.py", "prompts.py", "validator.py", "webui.py", "serving.py"]
REQUIREMENTS = "gradio==6.28.0\nopenai==3.16.2\n"    # the versions the page was tested with
CRLF_SUFFIXES = {".bat", ".ps1", ".txt"}              # Windows-native text; the launcher is ASCII
PACKAGE_DIR = "VietPoet"


def app_files() -> dict[str, bytes]:
    files = {f"app/{name}": (ROOT / "app" / name).read_bytes() for name in APP_FILES}
    files["requirements.txt"] = REQUIREMENTS.encode()
    return files


def collect_mac() -> dict[str, bytes]:
    files = app_files()
    files["Start VietPoet.command"] = (MAC / "Start VietPoet.command").read_bytes()
    files["Change model or hardware.command"] = (MAC / "Change model or hardware.command").read_bytes()
    files["launcher/start.sh"] = (MAC / "start.sh").read_bytes()
    files["README.txt"] = (MAC / "README.txt").read_bytes()
    for path, data in files.items():            # bash 3.2 on macOS dislikes CRLF; the repo may have been checked out on Windows
        if path.endswith((".sh", ".command", ".txt")):
            files[path] = data.replace(b"\r\n", b"\n")
    return files


def collect_win() -> dict[str, bytes]:
    files = app_files()
    files["Start VietPoet.bat"] = (WIN / "Start VietPoet.bat").read_bytes()
    files["Change model or hardware.bat"] = (WIN / "Change model or hardware.bat").read_bytes()
    files["launcher/start.ps1"] = (WIN / "start.ps1").read_bytes()
    files["README.txt"] = (WIN / "README.txt").read_bytes()
    for path, data in list(files.items()):
        if Path(path).suffix in CRLF_SUFFIXES:
            files[path] = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return files


def write_zip(zip_path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for path, data in files.items():
            info = zipfile.ZipInfo(f"{PACKAGE_DIR}/{path}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            executable = path.endswith((".sh", ".command"))
            info.external_attr = (0o755 if executable else 0o644) << 16     # Unix mode: macOS needs the execute bit
            z.writestr(info, data)
    print(f"{zip_path}  ({zip_path.stat().st_size / 1024:.0f} KB, {len(files)} files)")
    for path in files:
        print("  ", path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["win", "mac", "all"], default="win")
    ap.add_argument("--out", default=str(ROOT / "dist"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.target in ("win", "all"):
        files = collect_win()
        for path, data in files.items():        # the launcher must stay ASCII (Windows PowerShell 5.1 has no UTF-8 default)
            if path.endswith(".ps1"):
                data.decode("ascii")
        write_zip(out / "VietPoet-win.zip", files)
    if args.target in ("mac", "all"):
        write_zip(out / "VietPoet-mac.zip", collect_mac())


if __name__ == "__main__":
    main()
