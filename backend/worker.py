"""R2 worker: python worker.py [--once]; optional daily backup via BACKUP_ENABLED=1."""
import argparse
import os
import time

from app.config import Settings
from app.database import build_database
from app.operations import process_mail, restore_to_empty_database, run_backup, run_daily_backup


def main():
    parser = argparse.ArgumentParser(description="寄信重試與每日備份；不建立或修改資料表")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--backup-now", action="store_true")
    parser.add_argument("--restore", metavar="FILE")
    parser.add_argument("--confirm-empty-target", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.restore:
        target = os.getenv("RESTORE_DATABASE_URL")
        if not args.confirm_empty_target or not target:
            parser.error("還原須設定 RESTORE_DATABASE_URL 並加 --confirm-empty-target；僅接受非現用的空資料庫")
        restore_to_empty_database(args.restore, target, settings.database_url)
        print("已還原至指定的獨立空資料庫。")
        return
    engine, sessions = build_database(settings.database_url)
    try:
        if args.backup_now:
            print(run_backup(sessions, settings))
            return
        while True:
            run_daily_backup(sessions, settings)
            process_mail(sessions, settings)
            if args.once:
                break
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
