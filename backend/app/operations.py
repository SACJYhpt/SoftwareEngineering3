"""R2 SMTP outbox and backup I/O. Run through worker.py, outside API transactions."""
from datetime import timedelta
from contextlib import closing
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4
import smtplib
import sqlite3
import ssl
import subprocess
import tempfile

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url

from .models import BackupRecord, EmailAttempt, OutgoingEmail, User
from .services import queue_email, utc_now


def smtp_send(settings, recipient, subject, body):
    if not settings.smtp_host:
        raise RuntimeError("SMTP_NOT_CONFIGURED")
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = settings.mail_from, recipient, subject
    message.set_content(body)
    client_type = smtplib.SMTP_SSL if settings.smtp_security == "ssl" else smtplib.SMTP
    options = {"timeout": 15}
    if settings.smtp_security == "ssl":
        options["context"] = ssl.create_default_context()
    with client_type(settings.smtp_host, settings.smtp_port, **options) as smtp:
        if settings.smtp_security == "starttls":
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


def process_mail(sessions, settings, limit=20):
    """Initial send + at least three automatic retries, with durable attempt logs.

    A five-minute lease permits recovery after a crashed worker. Delivery is
    at-least-once: SMTP cannot guarantee no duplicate after a crash post-send.
    """
    handled = 0
    for _ in range(limit):
        now = utc_now()
        with sessions() as db:
            if db.bind.dialect.name == "sqlite":
                db.execute(text("BEGIN IMMEDIATE"))
            mail = db.scalar(select(OutgoingEmail).where(
                OutgoingEmail.status.in_(["pending", "sending"]), OutgoingEmail.next_attempt_at <= now)
                .order_by(OutgoingEmail.id).with_for_update(skip_locked=True).limit(1))
            if mail is None:
                db.rollback()
                break
            mail.status = "sending"
            mail.next_attempt_at = now + timedelta(minutes=5)
            email_id, recipient, subject, body = mail.id, mail.recipient, mail.subject, mail.body
            db.commit()
        error = None
        try:
            smtp_send(settings, recipient, subject, body)
        except Exception as exc:
            # Never persist exception messages that may contain credentials or tokens.
            error = "SMTP_NOT_CONFIGURED" if not settings.smtp_host else type(exc).__name__
        with sessions.begin() as db:
            mail = db.scalar(select(OutgoingEmail).where(OutgoingEmail.id == email_id).with_for_update())
            mail.attempts += 1
            db.add(EmailAttempt(email_id=email_id, attempted_at=utc_now(), error=error))
            if error:
                mail.status = "failed" if mail.attempts >= 4 else "pending"
                mail.next_attempt_at = utc_now() + timedelta(seconds=60 * 2 ** (mail.attempts - 1))
            else:
                mail.status, mail.sent_at = "sent", utc_now()
        handled += 1
    return handled


def mysql_command(url, program, output=None, input_file=None):
    """Credentials go into a private temporary option file, never argv or logs."""
    url = make_url(url)
    def quoted(value):
        return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r') + '"'
    with tempfile.TemporaryDirectory(prefix="event-db-client-") as directory:
        defaults = Path(directory) / "client.cnf"
        defaults.write_text("[client]\n" + "\n".join(f"{key}={quoted(value)}" for key, value in {
            "host": url.host or "localhost", "port": url.port or 3306, "user": url.username or "",
            "password": url.password or "", "default-character-set": "utf8mb4"}.items()), encoding="utf-8")
        args = [program, "--defaults-extra-file=" + str(defaults)]
        if program == "mysqldump":
            args += ["--single-transaction", "--no-tablespaces", "--set-gtid-purged=OFF"]
        args += [url.database]
        subprocess.run(args, stdout=output, stdin=input_file, stderr=subprocess.PIPE, check=True, timeout=300)


def run_backup(sessions, settings):
    directory = Path(settings.backup_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    url = make_url(settings.database_url)
    suffix = ".sqlite" if url.get_backend_name() == "sqlite" else ".sql"
    filename = f"events-{now:%Y%m%dT%H%M%S}-{uuid4().hex[:8]}{suffix}"
    destination = directory / filename
    with sessions.begin() as db:
        record = BackupRecord(created_at=now, status="running", filename=filename)
        db.add(record)
        db.flush()
        record_id = record.id
    error = None
    try:
        if url.get_backend_name() == "sqlite":
            source = Path(url.database).resolve()
            if not source.is_file():
                raise RuntimeError("Database file does not exist")
            with closing(sqlite3.connect(source)) as connection, closing(sqlite3.connect(destination)) as backup:
                connection.backup(backup)
        elif url.get_backend_name() == "mysql":
            with destination.open("xb") as output:
                mysql_command(settings.database_url, "mysqldump", output=output)
        else:
            raise RuntimeError("Unsupported database")
    except Exception as exc:
        error = type(exc).__name__
        if destination.is_file():
            destination.unlink()
    with sessions.begin() as db:
        record = db.get(BackupRecord, record_id)
        record.status, record.error = ("failed" if error else "success"), error
        if error:
            for email in db.scalars(select(User.email).where(User.role == "admin", User.is_active.is_(True))):
                queue_email(db, email, "資料庫備份失敗", f"備份紀錄 {record_id} 失敗，錯誤類型：{error}。請查看維運紀錄。")
        for old in db.scalars(select(BackupRecord).where(BackupRecord.created_at < now - timedelta(days=7))):
            if old.filename and Path(old.filename).name == old.filename:
                path = (directory / old.filename).resolve()
                if path.is_relative_to(directory) and path.is_file():
                    path.unlink()
    return dict(id=record_id, status="failed" if error else "success", filename=filename)


def run_daily_backup(sessions, settings):
    if not settings.backup_enabled:
        return None
    from datetime import datetime, timezone
    taiwan = timezone(timedelta(hours=8))
    today = utc_now().replace(tzinfo=timezone.utc).astimezone(taiwan).date()
    start = datetime.combine(today, datetime.min.time(), taiwan).astimezone(timezone.utc).replace(tzinfo=None)
    with sessions() as db:
        already = db.scalar(select(BackupRecord.id).where(BackupRecord.created_at >= start).limit(1))
    return None if already else run_backup(sessions, settings)


def restore_to_empty_database(filename, target_url, source_url):
    """Explicit CLI operation, never exposed over HTTP; refuse existing data."""
    source, target = make_url(source_url), make_url(target_url)
    if source == target:
        raise ValueError("Restore target must differ from the active database")
    filename = Path(filename).resolve(strict=True)
    if target.get_backend_name() == "sqlite":
        destination = Path(target.database).resolve()
        if source.get_backend_name() == "sqlite" and destination == Path(source.database).resolve():
            raise ValueError("Restore target is the active database")
        if destination.exists():
            raise ValueError("Restore target must not exist")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(filename.as_uri() + "?mode=ro", uri=True)) as backup, closing(sqlite3.connect(destination)) as restored:
            backup.backup(restored)
    elif target.get_backend_name() == "mysql":
        if (source.host, source.port or 3306, source.database) == (target.host, target.port or 3306, target.database):
            raise ValueError("Restore target is the active database")
        engine = create_engine(target)
        try:
            if inspect(engine).get_table_names():
                raise ValueError("Restore target must be an empty database")
        finally:
            engine.dispose()
        with filename.open("rb") as data:
            mysql_command(target_url, "mysql", input_file=data)
    else:
        raise ValueError("Unsupported restore target")
