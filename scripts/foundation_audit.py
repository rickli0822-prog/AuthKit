"""Check that AuthKit foundation readiness gates are wired."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "docs/FOUNDATION_READINESS.md",
    "docs/RELEASE_CHECKLIST.md",
    "docs/SUPPORT_BUNDLE.md",
    "docs/FIELD_SAMPLE_REGRESSION.md",
    "docs/WINDOWS_INSTALLER.md",
    "scripts/release_smoke.py",
    "scripts/build_windows_installer.py",
    "scripts/field_repair_drill.py",
    "scripts/field_sample_regression.py",
    "src/authkit/cli.py",
    "src/authkit/shortcut.py",
    "src/authkit/ui/app.py",
    "src/authkit/assets/authkit.ico",
    "src/authkit/assets/authkit-icon-48.png",
]

RELEASE_SMOKE_HOOKS = [
    "scripts/field_repair_drill.py",
    "scripts/field_sample_regression.py",
    "authkit-shortcut",
    "--dry-run",
    "authkit-gui",
    "--smoke",
    "bundle",
    "--sample",
    "--validate",
    "pip",
    "wheel",
    "build_windows_installer.py",
    "--check-only",
]

FOUNDATION_DOC_TERMS = [
    "authkit --help",
    "authkit-gui --smoke",
    "authkit-shortcut --dry-run",
    "field_repair_drill.py",
    "field_sample_regression.py",
    "release_smoke.py",
    "build_windows_installer.py",
]


def main() -> int:
    failures: list[str] = []
    for relative in REQUIRED_FILES:
        path = REPO_ROOT / relative
        if not path.is_file():
            failures.append(f"missing required file: {relative}")

    sample_dir = REPO_ROOT / "docs" / "field_samples"
    samples = sorted(sample_dir.glob("*.json"))
    if not samples:
        failures.append("docs/field_samples must contain at least one sanitized sample JSON")

    release_smoke = _read("scripts/release_smoke.py", failures)
    for hook in RELEASE_SMOKE_HOOKS:
        if hook not in release_smoke:
            failures.append(f"release_smoke.py missing hook: {hook}")

    readiness = _read("docs/FOUNDATION_READINESS.md", failures)
    for term in FOUNDATION_DOC_TERMS:
        if term not in readiness:
            failures.append(f"FOUNDATION_READINESS.md missing term: {term}")

    if failures:
        print("AuthKit foundation audit failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("AuthKit foundation audit passed.")
    print(f"- required_files: {len(REQUIRED_FILES)}")
    print(f"- field_samples: {len(samples)}")
    print(f"- release_smoke_hooks: {len(RELEASE_SMOKE_HOOKS)}")
    return 0


def _read(relative: str, failures: list[str]) -> str:
    path = REPO_ROOT / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        failures.append(f"cannot read {relative}: {exc}")
        return ""


if __name__ == "__main__":
    raise SystemExit(main())
