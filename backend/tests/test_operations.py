"""R2 mail and backup acceptance: no external SMTP/MySQL credentials are used."""
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
import socketserver
import sqlite3
import threading

import pytest
from sqlalchemy import func, select

from app import operations
from app.models import BackupRecord, EmailAttempt, OutgoingEmail, User
from app.security import issue_token
from app.services import queue_email


@pytest.fixture
def clock(monkeypatch):
    state={'now':datetime(2030,1,10)}
    monkeypatch.setattr('app.operations.utc_now',lambda:state['now'])
    monkeypatch.setattr('app.services.utc_now',lambda:state['now'])
    return state


def enqueue(application):
    with application.state.sessions.begin() as db:
        queue_email(db,'recipient@test.invalid','測試通知','通知內容')


def admin_headers(application):
    return {'Authorization':'Bearer '+issue_token(4,application.state.settings)}


def test_retries_are_durable_and_recovery_sends_once(application,monkeypatch,clock):
    enqueue(application)
    calls=[]
    def sender(*args):
        calls.append(args)
        if len(calls)<3:
            raise OSError('mail server down')
    monkeypatch.setattr(operations,'smtp_send',sender)
    settings=replace(application.state.settings,smtp_host='local-test')
    for seconds in (0,60,120):
        clock['now']+=timedelta(seconds=seconds)
        assert operations.process_mail(application.state.sessions,settings)==1
    assert operations.process_mail(application.state.sessions,settings)==0
    with application.state.sessions() as db:
        mail=db.scalar(select(OutgoingEmail))
        assert mail.status=='sent' and mail.attempts==3
        assert db.scalar(select(func.count(EmailAttempt.id)))==3
        assert db.scalar(select(func.count(EmailAttempt.id)).where(EmailAttempt.error.is_not(None)))==2


def test_failed_after_three_retries_then_admin_manual_retry(application,client,headers,monkeypatch,clock):
    enqueue(application)
    def broken(*args): raise OSError('secret-must-not-be-logged')
    monkeypatch.setattr(operations,'smtp_send',broken)
    settings=replace(application.state.settings,smtp_host='local-test')
    for _ in range(4):
        assert operations.process_mail(application.state.sessions,settings)==1
        clock['now']+=timedelta(hours=1)
    assert operations.process_mail(application.state.sessions,settings)==0
    admin=admin_headers(application)
    assert client.get('/admin/emails',headers=headers).status_code==403
    failed=client.get('/admin/emails',params={'status':'failed'},headers=admin).json()
    assert len(failed)==1 and failed[0]['attempts']==4 and len(failed[0]['failures'])==4
    assert 'secret-must-not-be-logged' not in str(failed)
    assert 'body' not in failed[0]
    email_id=failed[0]['id']
    assert client.post(f'/admin/emails/{email_id}/retry',headers=headers).status_code==403
    assert client.post(f'/admin/emails/{email_id}/retry',headers=admin).status_code==202
    monkeypatch.setattr(operations,'smtp_send',lambda *args:None)
    assert operations.process_mail(application.state.sessions,settings)==1
    assert client.get('/admin/emails',params={'status':'sent'},headers=admin).json()[0]['id']==email_id
    with application.state.sessions() as db:
        assert db.scalar(select(func.count(EmailAttempt.id)))==5


def test_missing_smtp_is_not_reported_as_sent(application):
    enqueue(application)
    assert operations.process_mail(application.state.sessions,application.state.settings)==1
    with application.state.sessions() as db:
        assert db.scalar(select(OutgoingEmail.status))=='pending'
        assert db.scalar(select(EmailAttempt.error))=='SMTP_NOT_CONFIGURED'


def test_smtp_delivery_to_local_test_server(application):
    messages=[]
    class SMTP(socketserver.StreamRequestHandler):
        def handle(self):
            self.wfile.write(b'220 local-test\r\n')
            while True:
                line=self.rfile.readline()
                if not line: break
                command=line.upper()
                if command.startswith((b'EHLO',b'HELO')):
                    self.wfile.write(b'250 local-test\r\n')
                elif command.startswith(b'DATA'):
                    self.wfile.write(b'354 send data\r\n')
                    data=[]
                    while True:
                        part=self.rfile.readline()
                        if part==b'.\r\n' or not part: break
                        data.append(part)
                    messages.append(b''.join(data))
                    self.wfile.write(b'250 queued\r\n')
                elif command.startswith(b'QUIT'):
                    self.wfile.write(b'221 bye\r\n');break
                else:
                    self.wfile.write(b'250 ok\r\n')
    with socketserver.TCPServer(('127.0.0.1',0),SMTP) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            settings=replace(application.state.settings,smtp_host='127.0.0.1',smtp_port=server.server_address[1],smtp_security='none')
            enqueue(application)
            assert operations.process_mail(application.state.sessions,settings)==1
        finally:
            server.shutdown();thread.join(timeout=5)
    assert len(messages)==1 and b'recipient@test.invalid' in messages[0]
    with application.state.sessions() as db:
        assert db.scalar(select(OutgoingEmail.status))=='sent'


def test_sqlite_backup_restore_and_daily_schedule(application,client,headers,tmp_path,clock):
    settings=replace(application.state.settings,backup_dir=str(tmp_path/'backups'),backup_enabled=True)
    result=operations.run_daily_backup(application.state.sessions,settings)
    assert result['status']=='success'
    assert operations.run_daily_backup(application.state.sessions,settings) is None
    restored=tmp_path/'restore.db'
    operations.restore_to_empty_database(Path(settings.backup_dir)/result['filename'],f'sqlite:///{restored.as_posix()}',settings.database_url)
    with sqlite3.connect(restored) as db:
        assert db.execute('select count(*) from users').fetchone()[0]==5
        assert db.execute('select count(*) from unit_managers').fetchone()[0]==3
        assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
    with pytest.raises(ValueError):
        operations.restore_to_empty_database(Path(settings.backup_dir)/result['filename'],settings.database_url,settings.database_url)
    with pytest.raises(ValueError):
        operations.restore_to_empty_database(Path(settings.backup_dir)/result['filename'],f'sqlite:///{restored.as_posix()}',settings.database_url)
    assert client.get('/admin/backups',headers=headers).status_code==403
    assert client.get('/admin/backups',headers=admin_headers(application)).json()[0]['status']=='success'
    clock['now']+=timedelta(days=1)
    assert operations.run_daily_backup(application.state.sessions,settings)['status']=='success'


def test_backup_failure_queues_admin_notice_and_retention_is_safe(application,tmp_path,monkeypatch,clock):
    directory=tmp_path/'backups';directory.mkdir()
    old=directory/'old.sqlite';old.write_bytes(b'old')
    outside=tmp_path/'keep.txt';outside.write_text('keep')
    with application.state.sessions.begin() as db:
        db.add_all([BackupRecord(created_at=clock['now']-timedelta(days=8),status='success',filename='old.sqlite'),
                    BackupRecord(created_at=clock['now']-timedelta(days=8),status='success',filename='../keep.txt')])
    settings=replace(application.state.settings,database_url='mysql+pymysql://user:secret@127.0.0.1/test',backup_dir=str(directory))
    def failed(*args,**kwargs): raise FileNotFoundError('mysqldump unavailable')
    monkeypatch.setattr(operations,'mysql_command',failed)
    result=operations.run_backup(application.state.sessions,settings)
    assert result['status']=='failed'
    assert outside.read_text()=='keep' and not old.exists()
    with application.state.sessions() as db:
        mail=db.scalar(select(OutgoingEmail))
        assert mail.recipient=='admin@test.invalid' and '備份失敗' in mail.subject
        assert 'secret' not in mail.body


def test_mysql_client_command_keeps_password_out_of_arguments(monkeypatch,tmp_path):
    captured=[]
    def run(args,**kwargs):
        captured.append(args)
        assert 'secret-password' not in str(args)
        config=Path(args[1].split('=',1)[1]).read_text(encoding='utf-8')
        assert 'secret-password' in config and 'default-character-set' in config
        kwargs['stdout'].write(b'-- simulated mysql dump\n')
    monkeypatch.setattr(operations.subprocess,'run',run)
    with (tmp_path/'dump.sql').open('wb') as output:
        operations.mysql_command('mysql+pymysql://user:secret-password@localhost/test','mysqldump',output=output)
    assert '--single-transaction' in captured[0]
    assert not Path(captured[0][1].split('=',1)[1]).exists()
