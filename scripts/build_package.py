"""Build the Windows package for friends: dist/VietPoet-win.zip (app + launcher, no models, no private files).

    python scripts/build_package.py [--out dist]

The zip holds only the page code, a launcher and a README. The launcher downloads the GGUF model from
Hugging Face on first run and sets up Python through uv, so the zip stays a few hundred KB.
"""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIN = ROOT / "packaging" / "windows"
APP_FILES = ["__init__.py", "agent.py", "prompts.py", "validator.py", "webui.py", "serving.py"]
REQUIREMENTS = "gradio==6.28.0\nopenai==3.16.2\n"    # the versions the page was tested with
CRLF_SUFFIXES = {".bat", ".ps1", ".txt"}              # Windows-native text; the launcher is ASCII
PACKAGE_DIR = "VietPoet"


def collect() -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for name in APP_FILES:
        files[f"app/{name}"] = (ROOT / "app" / name).read_bytes()
    files["requirements.txt"] = REQUIREMENTS.encode()
    files["Start VietPoet.bat"] = (WIN / "Start VietPoet.bat").read_bytes()
    files["Change model or hardware.bat"] = (WIN / "Change model or hardware.bat").read_bytes()
    files["launcher/start.ps1"] = (WIN / "start.ps1").read_bytes()
    files["README.txt"] = (WIN / "README.txt").read_bytes()
    for path, data in list(files.items()):
        if Path(path).suffix in CRLF_SUFFIXES:
            files[path] = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return files


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dist"))
    out = Path(ap.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    zip_path = out / "VietPoet-win.zip"
    files = collect()
    for path, data in files.items():            # the launcher must stay ASCII (Windows PowerShell 5.1 has no UTF-8 default)
        if path.endswith(".ps1"):
            data.decode("ascii")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for path, data in files.items():
            z.writestr(f"{PACKAGE_DIR}/{path}", data)
    print(f"{zip_path}  ({zip_path.stat().st_size / 1024:.0f} KB, {len(files)} files)")
    for path in files:
        print("  ", path)


if __name__ == "__main__":
    main()
