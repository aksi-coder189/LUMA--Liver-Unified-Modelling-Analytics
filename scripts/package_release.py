"""Create a source ZIP without caches, credentials, or compiled Python files."""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".pyd", ".log", ".tmp", ".zip"}
REQUIRED = {
    "README.md",
    "requirements-dev.txt",
    "src/server.py",
    "src/train_synthetic.py",
    "model/synthetic_ode_model.json",
    "web/index.html",
}


def should_include(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(
        part in EXCLUDED_DIRS or part.startswith(("pytest-cache-files-", ".test-"))
        for part in relative.parts
    ):
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if path.name.startswith(".env") and path.name != ".env.example":
        return False
    if path.name in {".DS_Store", "Thumbs.db"}:
        return False
    return path.is_file()


def create_archive(destination: Path) -> int:
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"Release is missing required files: {', '.join(sorted(missing))}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in ROOT.rglob("*") if should_include(path))
    with ZipFile(
        destination, "w", compression=ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in files:
            archive.write(path, (Path(ROOT.name) / path.relative_to(ROOT)).as_posix())
    return len(files)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT.parent / "masld-digital-twin-release.zip"
    )
    args = parser.parse_args()
    destination = args.output.resolve()
    if destination == ROOT or ROOT in destination.parents:
        parser.error("output must be outside the project folder")
    try:
        count = create_archive(destination)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Created {destination} ({count} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
