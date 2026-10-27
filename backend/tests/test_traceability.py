"""TRACEABILITY.md lists every test plan case and points at tests that exist."""

import re
from collections import Counter
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROW = re.compile(r"^\| ((?:FR\d\.\d|SEC-[A-Z]+-\d)-(?:UT|IT|ST)-\d+) \| (\w+) \| (.*?) \| (.*) \|$")
STATUSES = {"Automated", "Partial", "Manual", "Pending"}
# Test Plan Document, section 3 summary table.
CASES_PER_MODULE = {
    "FR1": 24,
    "FR2": 40,
    "FR3": 32,
    "FR4": 24,
    "FR5": 24,
    "FR6": 40,
    "FR7": 16,
    "FR8": 16,
    "SEC": 10,
}


def table() -> dict[str, tuple[str, list[str], str]]:
    rows = {}
    for line in (TESTS_DIR / "TRACEABILITY.md").read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if match:
            case_id, status, tests, note = match.groups()
            assert case_id not in rows, f"{case_id} is listed twice"
            refs = [ref.strip().strip("`") for ref in tests.split(" ; ") if ref.strip()]
            rows[case_id] = (status, refs, note.strip())
    return rows


def test_every_case_in_the_plan_is_listed():
    counts = Counter(re.match(r"FR\d|SEC", case_id).group() for case_id in table())
    assert dict(counts) == CASES_PER_MODULE
    assert sum(counts.values()) == 226


def test_every_case_has_a_valid_status_and_reason():
    for case_id, (status, refs, note) in table().items():
        assert status in STATUSES, case_id
        if status == "Automated":
            assert refs, f"{case_id} is Automated but names no test"
        else:
            assert note, f"{case_id} is {status} and needs a note saying why"


def test_named_backend_tests_exist():
    source: dict[str, str] = {}
    for case_id, (_status, refs, _note) in table().items():
        for ref in refs:
            if ref.startswith("fe:"):
                continue  # the frontend is not mounted in the backend container
            name, _, function = ref.partition("::")
            path = TESTS_DIR / name
            assert path.is_file(), f"{case_id}: {name} does not exist"
            text = source.setdefault(name, path.read_text(encoding="utf-8"))
            assert re.search(rf"^def {function}\(", text, re.M), f"{case_id}: {ref} not found"


def test_every_test_written_for_the_plan_is_listed():
    text = (TESTS_DIR / "test_plan_cases.py").read_text(encoding="utf-8")
    listed = {ref.partition("::")[2] for _status, refs, _note in table().values() for ref in refs}
    assert set(re.findall(r"^def (test_\w+)\(", text, re.M)) <= listed
