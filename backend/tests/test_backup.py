import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts import backup, uptime
from scripts.backup import Config, backup_job, check_job, next_run, select_expired

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def stamp(days_ago: int, hour: int = 2) -> datetime:
    return (NOW - timedelta(days=days_ago)).replace(hour=hour, minute=0)


def make_fake_backup(path: Path, ts: datetime) -> Path:
    d = path / ts.strftime(backup.STAMP_FORMAT)
    d.mkdir(parents=True)
    return d


@pytest.fixture
def config(tmp_path: Path) -> Config:
    images = tmp_path / "product-images"
    images.mkdir()
    (images / "a.png").write_bytes(b"png-bytes")
    return Config(
        database_url="postgresql://x/y", backup_dir=tmp_path / "backups", image_dir=images
    )


@pytest.fixture
def fake_pg(monkeypatch):
    """Replace pg_dump / pg_restore with a writer of the --file argument."""
    calls = []

    def run_tool(args, database_url=""):
        calls.append(args)
        if args[0] == "pg_dump":
            Path(args[args.index("--file") + 1]).write_bytes(b"dump")

    monkeypatch.setattr(backup, "run_tool", run_tool)
    return calls


def test_retention_keeps_recent_and_first_of_each_old_month():
    stamps = [stamp(d) for d in (0, 1, 29, 31, 40, 45, 70, 400, 4000)]
    expired = select_expired(stamps, NOW, Config())
    kept = [s for s in stamps if s not in expired]
    # The last 30 days are kept. Of the three September backups (25th, 16th, 11th) only the first
    # of the month survives; older months keep one each; 4000 days is beyond 96 months.
    assert stamp(0) in kept and stamp(1) in kept and stamp(29) in kept
    assert stamp(45) in kept and stamp(31) not in kept and stamp(40) not in kept
    assert stamp(70) in kept and stamp(400) in kept
    assert stamp(4000) not in kept


def test_retention_never_deletes_the_newest_backup():
    old = [stamp(5000)]
    assert select_expired(old, NOW, Config()) == []


def test_backup_contains_dump_images_and_checksums(config, fake_pg):
    path = backup.make_backup(config, NOW)
    assert path.name == "20261026T120000Z"
    assert sorted(p.name for p in path.iterdir()) == ["SHA256SUMS", "db.dump", "images.tar.gz"]
    with tarfile.open(path / "images.tar.gz") as tar:
        assert "product-images/a.png" in tar.getnames()
    backup.verify(path)
    assert fake_pg[1][0] == "pg_restore"  # dump was checked for readability
    assert not list(config.backup_dir.glob(".tmp-*"))


def test_verify_detects_corruption(config, fake_pg):
    path = backup.make_backup(config, NOW)
    (path / "db.dump").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        backup.verify(path)


def test_failed_backup_leaves_nothing_and_alerts(config, monkeypatch):
    alerts = []
    monkeypatch.setattr(uptime, "send_alert", lambda cfg, subject, body: alerts.append(subject))

    def boom(args, database_url=""):
        raise RuntimeError("pg_dump: connection refused")

    monkeypatch.setattr(backup, "run_tool", boom)
    assert backup_job(config) is False
    assert alerts == ["[ESIMS] Database backup failed"]
    assert list(config.backup_dir.iterdir()) == []


def test_successful_job_prunes_and_does_not_alert(config, fake_pg, monkeypatch):
    alerts = []
    monkeypatch.setattr(uptime, "send_alert", lambda *a: alerts.append(a))
    old = make_fake_backup(config.backup_dir, datetime(2010, 1, 1, 2, tzinfo=UTC))
    assert backup_job(config) is True
    assert not old.exists()
    assert len(backup.list_backups(config.backup_dir)) == 1
    assert alerts == []


def test_check_flags_missing_and_stale_backups(config, monkeypatch):
    alerts = []
    monkeypatch.setattr(uptime, "send_alert", lambda cfg, subject, body: alerts.append(subject))
    assert check_job(config) is False  # none yet
    make_fake_backup(config.backup_dir, datetime.now(UTC) - timedelta(hours=60))
    assert check_job(config) is False
    make_fake_backup(config.backup_dir, datetime.now(UTC) - timedelta(hours=3))
    assert check_job(config) is True
    assert alerts == ["[ESIMS] Backup is overdue"] * 2


def test_next_run_is_the_next_occurrence_in_local_time():
    cfg = Config(timezone="Asia/Kolkata")  # run_at 02:00 IST = 20:30 UTC the day before
    assert next_run(datetime(2026, 10, 26, 12, 0, tzinfo=UTC), cfg) == datetime(
        2026, 10, 26, 20, 30, tzinfo=UTC
    )
    assert next_run(datetime(2026, 10, 26, 21, 0, tzinfo=UTC), cfg) == datetime(
        2026, 10, 27, 20, 30, tzinfo=UTC
    )


def test_restore_runs_pg_restore_and_unpacks_images(config, fake_pg):
    path = backup.make_backup(config, NOW)
    (config.image_dir / "a.png").unlink()
    backup.restore(config, path)
    assert fake_pg[-1][0] == "pg_restore" and "--single-transaction" in fake_pg[-1]
    assert fake_pg[-1][fake_pg[-1].index("--dbname") + 1] == "y"
    assert (config.image_dir / "a.png").read_bytes() == b"png-bytes"


def test_libpq_env_keeps_the_password_out_of_arguments():
    env = backup.libpq_env("postgresql://esims:p%40ss@db:5433/esims?sslmode=require")
    assert env == {
        "PGHOST": "db",
        "PGPORT": "5433",
        "PGUSER": "esims",
        "PGPASSWORD": "p@ss",
        "PGDATABASE": "esims",
        "PGSSLMODE": "require",
    }
