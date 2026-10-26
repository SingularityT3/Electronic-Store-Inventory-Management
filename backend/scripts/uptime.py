"""Uptime monitor (NFR-4).

    python -m scripts.uptime watch            poll the health endpoint, alert on outages
    python -m scripts.uptime report FROM TO   uptime for a period (dates, YYYY-MM-DD, inclusive)
    python -m scripts.uptime alert "message"  send an alert now (used by the backup job, #36)

Every poll is appended to a JSON-lines log. The uptime figure is the share of polls made during
store hours that succeeded; polls outside store hours are ignored. Alerts go to email (SMTP_*
and MONITOR_ALERT_TO) and/or a chat webhook (MONITOR_WEBHOOK_URL, Slack/Discord-compatible JSON).
Run it on a different host from the app to also catch whole-server outages.
"""

import argparse
import json
import logging
import os
import smtplib
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger("esims.monitor")


@dataclass(frozen=True)
class Config:
    health_url: str = "http://backend:8000/api/health"
    interval_seconds: int = 30
    timeout_seconds: int = 10
    # Alert after this many consecutive failed polls.
    failures_before_alert: int = 2
    log_path: Path = Path("/data/uptime/checks.jsonl")
    timezone: str = "UTC"
    # Store hours: "HH:MM-HH:MM" local time, on the weekdays listed (0 = Monday).
    open_time: dtime = dtime(9, 0)
    close_time: dtime = dtime(21, 0)
    open_days: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6)
    alert_to: str = ""
    webhook_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    smtp_from: str = "ESIMS monitor <no-reply@esims.local>"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Config":
        e = os.environ if env is None else env
        opens, closes = e.get("MONITOR_STORE_HOURS", "09:00-21:00").split("-")
        days = e.get("MONITOR_STORE_DAYS", "0,1,2,3,4,5,6")
        return cls(
            health_url=e.get("MONITOR_HEALTH_URL", cls.health_url),
            interval_seconds=int(e.get("MONITOR_INTERVAL_SECONDS", cls.interval_seconds)),
            timeout_seconds=int(e.get("MONITOR_TIMEOUT_SECONDS", cls.timeout_seconds)),
            failures_before_alert=int(e.get("MONITOR_FAILURES_BEFORE_ALERT", 2)),
            log_path=Path(e.get("MONITOR_LOG_PATH", str(cls.log_path))),
            timezone=e.get("MONITOR_TIMEZONE", "UTC"),
            open_time=dtime.fromisoformat(opens),
            close_time=dtime.fromisoformat(closes),
            open_days=tuple(int(d) for d in days.split(",") if d),
            alert_to=e.get("MONITOR_ALERT_TO", ""),
            webhook_url=e.get("MONITOR_WEBHOOK_URL", ""),
            smtp_host=e.get("SMTP_HOST", ""),
            smtp_port=int(e.get("SMTP_PORT", 587)),
            smtp_username=e.get("SMTP_USERNAME", ""),
            smtp_password=e.get("SMTP_PASSWORD", ""),
            smtp_starttls=e.get("SMTP_STARTTLS", "true").lower() == "true",
            smtp_from=e.get("SMTP_FROM", cls.smtp_from),
        )


def check_health(url: str, timeout: float) -> tuple[bool, str]:
    """One poll. Healthy means HTTP 200 from the health endpoint."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status == 200, f"HTTP {response.status}"
    except Exception as exc:  # HTTP errors (503), refused connections and timeouts alike
        return False, str(exc)


def in_store_hours(moment: datetime, config: Config) -> bool:
    local = moment.astimezone(ZoneInfo(config.timezone))
    return (
        local.weekday() in config.open_days and config.open_time <= local.time() < config.close_time
    )


def record(config: Config, moment: datetime, ok: bool, detail: str) -> None:
    config.log_path.parent.mkdir(parents=True, exist_ok=True)
    line = {"ts": moment.astimezone(UTC).isoformat(), "ok": ok, "detail": detail}
    with config.log_path.open("a") as f:
        f.write(json.dumps(line) + "\n")


def read_checks(path: Path) -> list[tuple[datetime, bool]]:
    if not path.exists():
        return []
    checks = []
    for line in path.read_text().splitlines():
        if line.strip():
            item = json.loads(line)
            checks.append((datetime.fromisoformat(item["ts"]), item["ok"]))
    return checks


def uptime_report(
    checks: list[tuple[datetime, bool]], start: datetime, end: datetime, config: Config
) -> dict[str, object]:
    """Uptime over [start, end): successful polls / polls made during store hours."""
    relevant = [ok for ts, ok in checks if start <= ts < end and in_store_hours(ts, config)]
    total, up = len(relevant), sum(relevant)
    return {
        "checks": total,
        "successful": up,
        "uptime_percent": round(100 * up / total, 3) if total else None,
    }


def send_alert(config: Config, subject: str, body: str) -> None:
    """Send to every configured channel; a failing channel must not stop the others."""
    logger.error("ALERT: %s - %s", subject, body)
    if config.webhook_url:
        try:
            payload = json.dumps({"text": f"{subject}\n{body}", "content": f"{subject}\n{body}"})
            request = urllib.request.Request(
                config.webhook_url,
                payload.encode(),
                {"Content-Type": "application/json"},
            )
            urllib.request.urlopen(request, timeout=10).close()
        except Exception:
            logger.exception("Webhook alert failed")
    if config.alert_to and config.smtp_host:
        try:
            message = EmailMessage()
            message["From"] = config.smtp_from
            message["To"] = config.alert_to
            message["Subject"] = subject
            message.set_content(body)
            with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10) as smtp:
                if config.smtp_starttls:
                    smtp.starttls()
                if config.smtp_username:
                    smtp.login(config.smtp_username, config.smtp_password)
                smtp.send_message(message)
        except Exception:
            logger.exception("Email alert failed")


class Watcher:
    """Tracks consecutive failures; alerts once per outage and once on recovery."""

    def __init__(self, config: Config):
        self.config = config
        self.failures = 0
        self.alerted = False

    def observe(self, ok: bool, detail: str, now: datetime) -> None:
        record(self.config, now, ok, detail)
        if ok:
            if self.alerted:
                send_alert(
                    self.config, "[ESIMS] Recovered", f"Health check passing again at {now:%H:%M}."
                )
            self.failures, self.alerted = 0, False
            return
        self.failures += 1
        if self.failures >= self.config.failures_before_alert and not self.alerted:
            self.alerted = True
            send_alert(
                self.config,
                "[ESIMS] DOWN: health check failing",
                f"{self.failures} consecutive failures of {self.config.health_url} "
                f"(last: {detail}) as of {now:%Y-%m-%d %H:%M} UTC.",
            )


def watch(config: Config) -> None:
    watcher = Watcher(config)
    while True:
        ok, detail = check_health(config.health_url, config.timeout_seconds)
        watcher.observe(ok, detail, datetime.now(UTC))
        time.sleep(config.interval_seconds)


def _day_start(day: str, config: Config) -> datetime:
    return datetime.combine(date.fromisoformat(day), dtime.min, ZoneInfo(config.timezone))


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="scripts.uptime")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("watch")
    report = sub.add_parser("report")
    report.add_argument("start")
    report.add_argument("end")
    alert = sub.add_parser("alert")
    alert.add_argument("message")
    args = parser.parse_args(argv)
    config = Config.from_env()
    if args.command == "watch":
        watch(config)
    elif args.command == "alert":
        send_alert(config, "[ESIMS] Alert", args.message)
    else:
        start = _day_start(args.start, config)
        end = _day_start(args.end, config) + timedelta(days=1)
        result = uptime_report(read_checks(config.log_path), start, end, config)
        print(json.dumps({"from": args.start, "to": args.end, **result}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
