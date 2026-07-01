"""Validate sanitized AuthKit field sample bundles."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from authkit.cli import _validate_support_bundle


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE_DIR = REPO_ROOT / "docs" / "field_samples"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run sanitized field sample regression checks")
    parser.add_argument("--samples", default=str(DEFAULT_SAMPLE_DIR), help="directory containing *.json support bundle samples")
    args = parser.parse_args(argv)

    sample_dir = Path(args.samples)
    samples = sorted(sample_dir.glob("*.json"))
    if not samples:
        print(f"No field sample bundles found in {sample_dir}", file=sys.stderr)
        return 1

    failures: list[str] = []
    for sample in samples:
        failures.extend(_validate_sample(sample))

    if failures:
        print("AuthKit field sample regression failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(f"AuthKit field sample regression passed: {len(samples)} sample(s).")
    for sample in samples:
        print(f"- {sample.name}")
    return 0


def _validate_sample(path: Path) -> list[str]:
    failures = [f"{path.name}: {problem}" for problem in _validate_support_bundle(path)]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return failures + [f"{path.name}: cannot read sample JSON: {exc}"]
    if not isinstance(data, dict):
        return failures + [f"{path.name}: sample root must be an object"]

    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    expected = metadata.get("expected") if isinstance(metadata.get("expected"), dict) else {}
    if not expected:
        failures.append(f"{path.name}: metadata.expected is required for regression samples")
        return failures

    diagnosis = data.get("diagnosis") if isinstance(data.get("diagnosis"), dict) else {}
    diagnosis_inner = diagnosis.get("diagnosis") if isinstance(diagnosis.get("diagnosis"), dict) else {}
    audit = data.get("repair_audit") if isinstance(data.get("repair_audit"), list) else []

    checks = {
        "client": data.get("client"),
        "diagnosis_status": diagnosis.get("status") or metadata.get("diagnosis_status"),
        "diagnosis_case": diagnosis_inner.get("case") or metadata.get("diagnosis_case"),
    }
    for key, actual in checks.items():
        wanted = expected.get(key)
        if wanted is not None and actual != wanted:
            failures.append(f"{path.name}: expected {key}={wanted!r}, got {actual!r}")

    expected_fix_id = expected.get("repair_fix_id")
    if expected_fix_id and not any(isinstance(record, dict) and record.get("fix_id") == expected_fix_id for record in audit):
        failures.append(f"{path.name}: expected repair audit fix_id={expected_fix_id!r}")

    return failures


if __name__ == "__main__":
    raise SystemExit(main())
