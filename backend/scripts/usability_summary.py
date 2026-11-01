"""Summarise usability session observations from ``docs/usability/session-results.csv``.

Usage in the backend container:
    python -m scripts.usability_summary /app/../docs/usability/session-results.csv

The repository is mounted at ``/app`` for the backend service, so the normal command is:
    docker compose run --rm --no-deps backend python -m scripts.usability_summary \
      /workspace/docs/usability/session-results.csv

For a local repository mount, pass the path to the CSV as seen inside the container.
"""

import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

FIELDS = [
    "participant_id",
    "role",
    "prior_experience",
    "task_id",
    "success",
    "time_seconds",
    "errors",
    "seq_1_to_7",
    "confusion_notes",
    "browser",
    "date",
]
SUCCESS_VALUES = {"unaided", "with_hint", "failed"}


def read_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != FIELDS:
                raise ValueError(f"CSV header must be exactly: {', '.join(FIELDS)}")
            rows = list(reader)
    except FileNotFoundError as exc:
        raise ValueError(f"CSV file not found: {path}") from exc
    for number, row in enumerate(rows, start=2):
        if any(row[field] is None for field in FIELDS):
            raise ValueError(f"row {number}: missing a required column")
        if not row["participant_id"] or not row["role"] or not row["task_id"]:
            raise ValueError(f"row {number}: participant_id, role and task_id are required")
        if row["success"] not in SUCCESS_VALUES:
            raise ValueError(f"row {number}: success must be unaided, with_hint or failed")
        try:
            if float(row["time_seconds"]) < 0:
                raise ValueError
            seq = float(row["seq_1_to_7"])
        except ValueError as exc:
            raise ValueError(f"row {number}: time_seconds and seq_1_to_7 must be numbers") from exc
        if not 1 <= seq <= 7:
            raise ValueError(f"row {number}: seq_1_to_7 must be between 1 and 7")
    return rows


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def render(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "No sessions have been run yet.\n"
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["task_id"]].append(row)
    lines = [
        "| Task | Attempts | Unaided success rate | With hint | Failed | Median seconds | "
        "Range seconds | Mean SEQ |",
        "|---|---:|---:|---:|---:|---:|---|---:|",
    ]
    for task_id in sorted(grouped):
        task_rows = grouped[task_id]
        times = [float(row["time_seconds"]) for row in task_rows]
        unaided = sum(row["success"] == "unaided" for row in task_rows)
        hinted = sum(row["success"] == "with_hint" for row in task_rows)
        failed = sum(row["success"] == "failed" for row in task_rows)
        lines.append(
            f"| {task_id} | {len(task_rows)} | {_fmt(unaided / len(task_rows) * 100)}% | "
            f"{hinted} | {failed} | {_fmt(statistics.median(times))} | "
            f"{_fmt(min(times))}-{_fmt(max(times))} | "
            f"{_fmt(statistics.mean(float(row['seq_1_to_7']) for row in task_rows))} |"
        )
    lines.extend(["", "| Role | Participants | Tasks | Verdict |", "|---|---:|---:|---|"])
    role_participants: dict[str, set[str]] = defaultdict(set)
    role_tasks: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        role_participants[row["role"]].add(row["participant_id"])
        role_tasks[row["role"]][row["task_id"]].append(row)
    for role in sorted(role_tasks):
        verdict = all(
            sum(row["success"] == "unaided" for row in task_rows) > len(task_rows) / 2
            for task_rows in role_tasks[role].values()
        )
        lines.append(
            f"| {role} | {len(role_participants[role])} | {len(role_tasks[role])} | "
            f"{'Pass: most users unaided' if verdict else 'Open: most users not unaided'} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("Usage: python -m scripts.usability_summary PATH", file=sys.stderr)
        return 2
    try:
        print(render(read_rows(Path(args[0]))), end="")
    except ValueError as exc:
        print(f"Invalid usability CSV: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
