"""Daily backups and restore (NFR-5).

    python -m scripts.backup watch                run a backup every day at BACKUP_TIME
    python -m scripts.backup run                  take one backup now
    python -m scripts.backup check                exit 1 (and alert) if the newest backup is too old
    python -m scripts.backup restore STAMP        restore a backup into DATABASE_URL and the images

A backup is a directory BACKUP_DIR/<UTC timestamp>/ holding `db.dump` (pg_dump custom format),
`images.tar.gz` (the product image directory) and `SHA256SUMS`. It is built in a temporary
directory and renamed when complete, so a listed backup is always whole. Failures are reported
through the uptime monitor's alert channels (email / webhook). Needs pg_dump and pg_restore on the
PATH, so it runs in the `backup` container (backend/Dockerfile.backup).
"""

import argparse
import hashlib
import logging
import os
import shutil
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from zoneinfo import ZoneInfo

from scripts import uptime

logger = logging.getLogger("esims.backup")

STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
TMP_PREFIX = ".tmp-"


@dataclass(frozen=True)
class Config:
    database_url: str = ""
    backup_dir: Path = Path("/backups")
    image_dir: Path = Path("/data/product-images")
    # Daily run time, local to `timezone`.
    run_at: dtime = dtime(2, 0)
    timezone: str = "UTC"
    # Every backup from the last `keep_daily_days` days is kept; older ones are thinned to the
    # first backup of each month, kept for `keep_monthly` months (96 = the 8 years of SRS A-2).
    keep_daily_days: int = 30
    keep_monthly: int = 96
    # `check` fails if the newest backup is older than this.
    max_age_hours: int = 26

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Config":
        e = os.environ if env is None else env
        return cls(
            database_url=e.get("DATABASE_URL", ""),
            backup_dir=Path(e.get("BACKUP_DIR", str(cls.backup_dir))),
            image_dir=Path(e.get("PRODUCT_IMAGE_DIR", str(cls.image_dir))),
            run_at=dtime.fromisoformat(e.get("BACKUP_TIME", "02:00")),
            timezone=e.get("BACKUP_TIMEZONE", "UTC"),
            keep_daily_days=int(e.get("BACKUP_KEEP_DAILY_DAYS", cls.keep_daily_days)),
            keep_monthly=int(e.get("BACKUP_KEEP_MONTHLY", cls.keep_monthly)),
            max_age_hours=int(e.get("BACKUP_MAX_AGE_HOURS", cls.max_age_hours)),
        )


def parse_stamp(name: str) -> datetime | None:
    try:
        return datetime.strptime(name, STAMP_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


def list_backups(backup_dir: Path) -> list[tuple[datetime, Path]]:
    """Complete backups, oldest first."""
    if not backup_dir.exists():
        return []
    found = [(parse_stamp(p.name), p) for p in backup_dir.iterdir() if p.is_dir()]
    return sorted((ts, p) for ts, p in found if ts is not None)


def select_expired(stamps: list[datetime], now: datetime, config: Config) -> list[datetime]:
    """Backups to delete under the retention policy. The newest backup is never deleted."""
    cutoff = now - timedelta(days=config.keep_daily_days)
    keep: set[datetime] = {max(stamps)} if stamps else set()
    seen_months: set[tuple[int, int]] = set()
    for ts in sorted(stamps):
        if ts >= cutoff:
            keep.add(ts)
            continue
        month = (ts.year, ts.month)
        if month not in seen_months:
            seen_months.add(month)
            age_months = (now.year - ts.year) * 12 + now.month - ts.month
            if age_months <= config.keep_monthly:
                keep.add(ts)
    return [ts for ts in stamps if ts not in keep]


def prune(config: Config, now: datetime) -> list[str]:
    backups = list_backups(config.backup_dir)
    expired = set(select_expired([ts for ts, _ in backups], now, config))
    removed = []
    for ts, path in backups:
        if ts in expired:
            shutil.rmtree(path)
            removed.append(path.name)
    return removed


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def libpq_env(database_url: str) -> dict[str, str]:
    """Connection settings as PG* variables, so the password stays out of command lines and logs."""
    url = urlparse(database_url)
    env = {
        "PGHOST": url.hostname or "",
        "PGPORT": str(url.port or 5432),
        "PGUSER": unquote(url.username or ""),
        "PGPASSWORD": unquote(url.password or ""),
        "PGDATABASE": url.path.lstrip("/"),
    }
    if sslmode := parse_qs(url.query).get("sslmode"):
        env["PGSSLMODE"] = sslmode[0]
    return env


def run_tool(args: list[str], database_url: str = "") -> None:
    env = {**os.environ, **libpq_env(database_url)} if database_url else None
    subprocess.run(args, check=True, capture_output=True, text=True, env=env)


def make_backup(config: Config, now: datetime) -> Path:
    """Dump the database and archive the images. Returns the finished backup directory."""
    stamp = now.strftime(STAMP_FORMAT)
    final = config.backup_dir / stamp
    if final.exists():
        raise FileExistsError(f"backup {stamp} already exists")
    config.backup_dir.mkdir(parents=True, exist_ok=True)
    work = config.backup_dir / f"{TMP_PREFIX}{stamp}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    try:
        dump = work / "db.dump"
        run_tool(["pg_dump", "--format=custom", "--file", str(dump)], config.database_url)
        run_tool(["pg_restore", "--list", str(dump)])  # unreadable dump -> fail now, not at restore
        images = work / "images.tar.gz"
        with tarfile.open(images, "w:gz") as tar:
            if config.image_dir.exists():
                tar.add(config.image_dir, arcname=config.image_dir.name)
        sums = "".join(f"{sha256(p)}  {p.name}\n" for p in (dump, images))
        (work / "SHA256SUMS").write_text(sums)
        work.rename(final)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    return final


def clear_stale_tmp(config: Config) -> None:
    """Remove half-written backups left by a crash."""
    if config.backup_dir.exists():
        for p in config.backup_dir.glob(f"{TMP_PREFIX}*"):
            shutil.rmtree(p, ignore_errors=True)


def verify(backup: Path) -> None:
    """Raise if a file does not match SHA256SUMS."""
    for line in (backup / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        if sha256(backup / name) != digest:
            raise ValueError(f"checksum mismatch: {backup.name}/{name}")


def restore(config: Config, backup: Path) -> None:
    """Replace the database contents and image files with those in `backup`.

    The target database must exist (it may be empty). Run it with the application stopped.
    """
    verify(backup)
    run_tool(
        [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--exit-on-error",
            "--single-transaction",
            "--dbname",
            libpq_env(config.database_url)["PGDATABASE"],  # without it pg_restore only prints SQL
            str(backup / "db.dump"),
        ],
        config.database_url,
    )
    with tarfile.open(backup / "images.tar.gz") as tar:
        # "data" filter refuses absolute paths, links outside the tree and similar tricks.
        tar.extractall(config.image_dir.parent, filter="data")


def backup_job(config: Config, alert: bool = True) -> bool:
    """One scheduled run: backup, prune, alert on failure. Returns success."""
    now = datetime.now(UTC)
    try:
        clear_stale_tmp(config)
        path = make_backup(config, now)
        removed = prune(config, now)
        logger.info("Backup %s done; pruned %s", path.name, removed or "nothing")
        return True
    except Exception as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        logger.exception("Backup failed")
        if alert:
            uptime.send_alert(
                uptime.Config.from_env(),
                "[ESIMS] Database backup failed",
                f"The {now:%Y-%m-%d} backup did not complete: {detail}",
            )
        return False


def newest_age(config: Config, now: datetime) -> timedelta | None:
    backups = list_backups(config.backup_dir)
    return now - backups[-1][0] if backups else None


def check_job(config: Config, alert: bool = True) -> bool:
    """True if the newest backup is recent enough; otherwise alert."""
    now = datetime.now(UTC)
    age = newest_age(config, now)
    if age is not None and age <= timedelta(hours=config.max_age_hours):
        return True
    state = "no backup exists" if age is None else f"the newest backup is {age} old"
    logger.error("Backup check failed: %s", state)
    if alert:
        uptime.send_alert(
            uptime.Config.from_env(),
            "[ESIMS] Backup is overdue",
            f"Expected a backup within {config.max_age_hours} h, but {state}.",
        )
    return False


def next_run(now: datetime, config: Config) -> datetime:
    tz = ZoneInfo(config.timezone)
    local = now.astimezone(tz)
    candidate = datetime.combine(local.date(), config.run_at, tz)
    if candidate <= local:
        candidate = datetime.combine(local.date() + timedelta(days=1), config.run_at, tz)
    return candidate.astimezone(UTC)


def watch(config: Config) -> None:
    while True:
        due = next_run(datetime.now(UTC), config)
        logger.info("Next backup at %s", due.isoformat())
        while (remaining := (due - datetime.now(UTC)).total_seconds()) > 0:
            time.sleep(min(remaining, 60))
        backup_job(config)
        # An overdue backup (e.g. the job kept failing) is reported again at the next run.
        check_job(config)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="scripts.backup")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("watch")
    sub.add_parser("run")
    sub.add_parser("check")
    restore_cmd = sub.add_parser("restore")
    restore_cmd.add_argument("stamp", help="backup directory name, e.g. 20261026T020000Z")
    args = parser.parse_args(argv)
    config = Config.from_env()
    if args.command == "watch":
        watch(config)
        return 0
    if args.command == "run":
        return 0 if backup_job(config) else 1
    if args.command == "check":
        return 0 if check_job(config, alert=False) else 1
    restore(config, config.backup_dir / args.stamp)
    logger.info("Restored %s", args.stamp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
