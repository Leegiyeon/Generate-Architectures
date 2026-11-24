"""Bundle the existing analyzer and static UI for browser-only hosting."""
import argparse
import hashlib
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile
from urllib.request import urlopen
from zipfile import ZIP_DEFLATED, ZipFile


MODULES = (
    "preview_fastapi_pr.py", "preview_migration_evidence.py",
    "fastapi_routes.py", "python_module_scope.py", "sqlmodel_models.py",
    "pr_preview_browser.py", "pr_preview_structure.py", "repository_structure.py",
)
RUNTIME_BASE = "https://cdn.jsdelivr.net/pyodide/v314.0.4/full/"
RUNTIME_FILES = {
    "pyodide.mjs": "c75dd73bb0c70674135f9f4ab746c9b5316e9fe027cafacb2be445e658f04c92",
    "pyodide.asm.mjs": "fd7a3cefa122ff6463dcf2997961eb341250e4cc4ed60281448390f0a767cca2",
    "pyodide.asm.wasm": "6c8986a8ee583401069aa403e76ee79d4633a1478ab11cea76030bc299aded9f",
    "python_stdlib.zip": "b5ca2308e9fa72eda319889a1ddf086389e9f1234ced279cc71267fe9ba56e54",
    "pyodide-lock.json": "c963d22858f6bcb8f41586a2142f03905ab370c88ea22a86a2736e95fac2a8f3",
}
RUNTIME_LICENSE_URL = "https://raw.githubusercontent.com/pyodide/pyodide/314.0.4/LICENSE"
RUNTIME_LICENSE_SHA = "1f256ecad192880510e84ad60474eab7589218784b9a50bc7ceee34c2b91f1d5"


def runtime_files(output):
    """Pin and host the minimal runtime, avoiding third-party browser script loading."""
    runtime = output / "pyodide"
    runtime.mkdir(exist_ok=True)
    for name, digest in {**RUNTIME_FILES, "LICENSE": RUNTIME_LICENSE_SHA}.items():
        target = runtime / name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
            continue
        url = RUNTIME_LICENSE_URL if name == "LICENSE" else RUNTIME_BASE + name
        with urlopen(url, timeout=60) as response:
            content = response.read(25 * 1024 * 1024)
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError(f"Runtime integrity check failed: {name}")
        target.write_bytes(content)


def build(output):
    root = Path(__file__).resolve().parent.parent
    output.mkdir(parents=True, exist_ok=True)
    for path in (root / "app/pr_preview").iterdir():
        if path.is_file():
            shutil.copyfile(path, output / path.name)
    modules = output / "analyzer"
    modules.mkdir(exist_ok=True)
    for name in MODULES:
        shutil.copyfile(root / "scripts" / name, modules / name)
    runtime_files(output)
    print(output.resolve())


def package(output, archive):
    """Include only declared web assets and a loopback-only local launcher."""
    root = Path(__file__).resolve().parent.parent
    output, archive = output.resolve(), archive.resolve()
    if archive.suffix.lower() != ".zip":
        raise ValueError("Archive output must have a .zip extension")
    if archive.is_relative_to(output):
        raise ValueError("Archive output must be outside the web output directory")
    assets = [Path(path.name) for path in (root / "app/pr_preview").iterdir() if path.is_file()]
    assets += [Path("analyzer") / name for name in MODULES]
    assets += [Path("pyodide") / name for name in (*RUNTIME_FILES, "LICENSE")]
    # Check all inputs before replacing an existing archive.
    for path in assets:
        if not (output / path).is_file():
            raise FileNotFoundError(output / path)
    launchers = root / "app/pr_preview_local"
    for name in ("start.py", "START.command", "README.txt"):
        if not (launchers / name).is_file():
            raise FileNotFoundError(launchers / name)
    sources = [root / "app/pr_preview" / path.name for path in assets if len(path.parts) == 1]
    sources += [root / "scripts" / name for name in MODULES]
    sources += [launchers / name for name in ("start.py", "START.command", "README.txt")]
    if archive in {path.resolve() for path in sources}:
        raise ValueError("Archive output must not replace a source file")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(prefix=f".{archive.name}.", suffix=".tmp", dir=archive.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with ZipFile(temporary_path, "w", compression=ZIP_DEFLATED) as bundle:
            for path in sorted(assets):
                bundle.write(output / path, Path("fastapi-pr-review/site") / path)
            for name in ("start.py", "START.command", "README.txt"):
                bundle.write(launchers / name, Path("fastapi-pr-review") / name)
        temporary_path.replace(archive)
    finally:
        temporary_path.unlink(missing_ok=True)
    print(archive.resolve())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path, help="Also package a local-run ZIP (Python 3.10+)")
    args = parser.parse_args()
    build(args.output)
    if args.archive:
        package(args.output, args.archive)
