from pathlib import Path

import pytest

from scripts.usability_summary import FIELDS, read_rows, render


def write_csv(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    path = tmp_path / "sessions.csv"
    path.write_text(
        ",".join(FIELDS)
        + "\n"
        + "\n".join(",".join(row[field] for field in FIELDS) for row in rows)
        + ("\n" if rows else ""),
        encoding="utf-8",
    )
    return path


def row(participant: str, role: str, task: str, success: str, seconds: str, seq: str):
    return {
        "participant_id": participant,
        "role": role,
        "prior_experience": "shop",
        "task_id": task,
        "success": success,
        "time_seconds": seconds,
        "errors": "",
        "seq_1_to_7": seq,
        "confusion_notes": "",
        "browser": "Chrome",
        "date": "2026-11-01",
    }


def test_empty_csv_is_explicit(tmp_path):
    assert render(read_rows(write_csv(tmp_path, []))) == "No sessions have been run yet.\n"


def test_summary_handles_median_range_hints_failures_and_exact_verdict(tmp_path):
    rows = [
        row("p1", "cashier", "sale", "unaided", "10", "6"),
        row("p2", "cashier", "sale", "with_hint", "20", "4"),
        row("p3", "cashier", "sale", "failed", "30", "2"),
        row("p1", "cashier", "return", "unaided", "8", "5"),
        row("p2", "cashier", "return", "failed", "12", "3"),
    ]
    output = render(read_rows(write_csv(tmp_path, rows)))
    assert "| sale | 3 | 33.33% | 1 | 1 | 20 | 10-30 | 4 |" in output
    assert "| cashier | 3 | 2 | Open: most users not unaided |" in output


def test_summary_verdict_requires_more_than_half(tmp_path):
    rows = [
        row("p1", "staff", "stock", "unaided", "10", "5"),
        row("p2", "staff", "stock", "unaided", "11", "5"),
        row("p3", "staff", "stock", "with_hint", "12", "5"),
    ]
    assert "Pass: most users unaided" in render(read_rows(write_csv(tmp_path, rows)))


def test_malformed_rows_are_rejected(tmp_path):
    path = write_csv(tmp_path, [row("p1", "staff", "stock", "unknown", "10", "5")])
    with pytest.raises(ValueError, match="success must be"):
        read_rows(path)
