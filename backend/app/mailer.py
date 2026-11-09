"""SMTP adapter. Development captures links for local testing; production requires SMTP."""
from email.message import EmailMessage
import smtplib


def send_link(settings, outbox, recipient, subject, body):
    if settings.smtp_host and settings.smtp_from:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings.smtp_from
        message["To"] = recipient
        message.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            if settings.smtp_starttls:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
        return
    if settings.app_env != "development":
        raise RuntimeError("正式環境必須設定 SMTP_HOST 與 SMTP_FROM，才能安全寄送驗證或重設連結。")
    # Local development convenience; never return tokens in public API responses.
    outbox.append({"to": recipient, "subject": subject, "body": body})
    print(f"\n[DEV EMAIL] To: {recipient}\nSubject: {subject}\n{body}\n")
