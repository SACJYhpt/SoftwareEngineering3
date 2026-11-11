"""Legacy import adapter retained from the teammate branch.

The running API uses services.queue_email and worker.py. This old callable is
not used by any route; delegate to the same SMTP primitive rather than keeping
a second implementation or printing private account links to the terminal.
"""
from .operations import smtp_send


def send_link(settings, outbox, recipient, subject, body):
    smtp_send(settings, recipient, subject, body)
