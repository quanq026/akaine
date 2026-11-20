"""Refresh stored Best 50 PTT while preserving score and play history."""
import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3

from core.ptt_v7 import best_potential, stored_potential


def changes(cursor):
    users = cursor.execute('SELECT user_id, rating_ptt FROM user').fetchall()
    updates = []
    for user_id, old in users:
        value = stored_potential(best_potential(cursor, user_id))
        if value != old:
            updates.append((value, user_id))
    return len(users), updates


def recompute(database, backup=None):
    database = database.resolve(strict=True)
    mode = 'rw' if backup is not None else 'ro'
    with closing(sqlite3.connect(f'{database.as_uri()}?mode={mode}', uri=True, timeout=20)) as db:
        db.execute('BEGIN IMMEDIATE' if backup is not None else 'BEGIN')
        count, updates = changes(db.cursor())
        if backup is None or not updates:
            return count, len(updates)
        descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        with closing(sqlite3.connect(f'{database.as_uri()}?mode=ro', uri=True)) as source, closing(sqlite3.connect(backup)) as snapshot:
            source.backup(snapshot)
            if snapshot.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise RuntimeError('SQLite backup failed its integrity check')
        db.executemany('UPDATE user SET rating_ptt=? WHERE user_id=?', updates)
        db.commit()
        return count, len(updates)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('--backup', type=Path, help='Apply changes and save the old DB to this new file')
    args = parser.parse_args()
    try:
        count, updated = recompute(args.database, args.backup)
    except (OSError, sqlite3.Error, RuntimeError) as error:
        parser.exit(1, f'PTT update stopped: {error}\n')
    mode = 'Applied' if args.backup is not None else 'Preview'
    print(f'{mode}: {updated} of {count} accounts need new PTT.')
    if args.backup is not None and updated:
        print(f'Backup: {args.backup.resolve()}')


if __name__ == '__main__':
    main()
