from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts import uptime
from scripts.uptime import Config, Watcher, in_store_hours, read_checks, uptime_report


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, day, hour, minute, tzinfo=UTC)  # 2026-03-02 is a Monday


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(log_path=tmp_path / "checks.jsonl", alert_to="ops@example.com")


def test_store_hours(config):
    assert in_store_hours(at(2, 9), config)
    assert not in_store_hours(at(2, 21), config)
    assert not in_store_hours(at(2, 3), config)
    weekdays = Config(open_days=(0, 1, 2, 3, 4))
    assert not in_store_hours(at(7, 12), weekdays)  # Saturday


def test_uptime_counts_only_store_hours(config):
    checks = [(at(2, 10), True), (at(2, 11), False), (at(2, 12), True), (at(2, 12, 30), True)]
    checks += [(at(2, 2), False)]  # night outage does not count
    result = uptime_report(checks, at(2, 0), at(3, 0), config)
    assert result == {"checks": 4, "successful": 3, "uptime_percent": 75.0}
    assert uptime_report(checks, at(4, 0), at(5, 0), config)["uptime_percent"] is None


def test_outage_alerts_once_then_recovery(config, monkeypatch):
    alerts = []
    monkeypatch.setattr(uptime, "send_alert", lambda c, subject, body: alerts.append(subject))
    watcher = Watcher(config)
    watcher.observe(False, "HTTP 503", at(2, 10, 0))
    assert alerts == []  # one failure is not yet an outage
    watcher.observe(False, "HTTP 503", at(2, 10, 1))
    watcher.observe(False, "HTTP 503", at(2, 10, 2))
    assert alerts == ["[ESIMS] DOWN: health check failing"]
    watcher.observe(True, "HTTP 200", at(2, 10, 3))
    assert alerts[-1] == "[ESIMS] Recovered"
    assert len(read_checks(config.log_path)) == 4


def test_check_health_reports_unreachable_as_down():
    ok, detail = uptime.check_health("http://127.0.0.1:1/api/health", 1)
    assert not ok and detail


def test_config_from_env():
    config = Config.from_env(
        {
            "MONITOR_STORE_HOURS": "08:30-18:00",
            "MONITOR_STORE_DAYS": "0,1",
            "MONITOR_TIMEZONE": "Asia/Kolkata",
        }
    )
    assert (config.open_time.hour, config.open_time.minute, config.close_time.hour) == (8, 30, 18)
    assert config.open_days == (0, 1)
