"""Persisted, single-instance workflow state for CHARBON TEST."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, time
from pathlib import Path


class Store:
    def __init__(self, path: str):
        self.path = path
        if path != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS posts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              local_day TEXT NOT NULL UNIQUE,
              body TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','approved','editing','rejected',
                                 'expired','publishing','published','failed')),
              preview_message_id INTEGER,
              channel_message_id INTEGER,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS usage (
              user_id INTEGER NOT NULL,
              local_day TEXT NOT NULL,
              count INTEGER NOT NULL DEFAULT 0,
              last_request INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY(user_id,local_day)
            );
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create_post(self, day: str, body: str):
        """Create at most one draft per local day. Return (post, created)."""
        with self._db() as db:
            cur = db.execute('INSERT OR IGNORE INTO posts(local_day,body) VALUES (?,?)', (day, body))
            created = cur.rowcount == 1
            post = db.execute('SELECT * FROM posts WHERE local_day=?', (day,)).fetchone()
            return dict(post), created

    def get_post(self, post_id: int):
        with self._db() as db:
            row = db.execute('SELECT * FROM posts WHERE id=?', (post_id,)).fetchone()
            return dict(row) if row else None

    def recent_bodies(self, limit: int = 5):
        with self._db() as db:
            return [row['body'] for row in db.execute(
                'SELECT body FROM posts ORDER BY id DESC LIMIT ?', (limit,))]

    def mark_preview(self, post_id: int, message_id: int):
        with self._db() as db:
            db.execute('UPDATE posts SET preview_message_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                       (message_id, post_id))

    def decide(self, post_id: int, action: str, now: datetime):
        """Transitions require same calendar day and before 10:00 Paris time.

        Return True only for a successful atomic transition; stale buttons fail.
        """
        new_status = {'approve': 'approved', 'edit': 'editing', 'reject': 'rejected'}.get(action)
        if not new_status or now.time().replace(tzinfo=None) >= time(10, 0):
            return False
        old_states = ('pending', 'approved') if action != 'approve' else ('pending',)
        with self._db() as db:
            marks = ','.join('?' for _ in old_states)
            cur = db.execute(
                f'''UPDATE posts SET status=?,updated_at=CURRENT_TIMESTAMP
                    WHERE id=? AND local_day=? AND status IN ({marks})''',
                (new_status, post_id, now.date().isoformat(), *old_states))
            return cur.rowcount == 1

    def pending_edit(self, day: str):
        with self._db() as db:
            row = db.execute("SELECT * FROM posts WHERE local_day=? AND status='editing'", (day,)).fetchone()
            return dict(row) if row else None

    def replace_edit(self, post_id: int, day: str, body: str, now: datetime):
        if now.time().replace(tzinfo=None) >= time(10, 0):
            return False
        with self._db() as db:
            cur = db.execute('''UPDATE posts SET body=?,status='pending',updated_at=CURRENT_TIMESTAMP
                                WHERE id=? AND local_day=? AND status='editing' ''',
                             (body, post_id, day))
            return cur.rowcount == 1

    def expire_unapproved(self, day: str):
        with self._db() as db:
            db.execute("UPDATE posts SET status='expired', updated_at=CURRENT_TIMESTAMP "
                       "WHERE local_day=? AND status IN ('pending','editing')", (day,))

    def claim_publication(self, day: str):
        """At-most-one send attempt; failures are held for manual inspection."""
        with self._db() as db:
            cur = db.execute("UPDATE posts SET status='publishing',updated_at=CURRENT_TIMESTAMP "
                             "WHERE local_day=? AND status='approved'", (day,))
            if cur.rowcount != 1:
                return None
            return dict(db.execute('SELECT * FROM posts WHERE local_day=?', (day,)).fetchone())

    def finish_publication(self, post_id: int, message_id: int | None):
        status = 'published' if message_id is not None else 'failed'
        with self._db() as db:
            db.execute("UPDATE posts SET status=?,channel_message_id=?,updated_at=CURRENT_TIMESTAMP "
                       "WHERE id=? AND status='publishing'", (status, message_id, post_id))

    def check_quota(self, user_id: int, day: str, epoch: int,
                    daily_limit: int = 12, cooldown_seconds: int = 20):
        """Persist rate limits without storing member message contents."""
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT count,last_request FROM usage WHERE user_id=? AND local_day=?',
                             (user_id,day)).fetchone()
            if row and (row['count'] >= daily_limit or epoch-row['last_request'] < cooldown_seconds):
                return False
            db.execute('''INSERT INTO usage(user_id,local_day,count,last_request) VALUES (?,?,1,?)
                          ON CONFLICT(user_id,local_day) DO UPDATE SET
                            count=usage.count+1,last_request=excluded.last_request''',
                       (user_id,day,epoch))
            return True
