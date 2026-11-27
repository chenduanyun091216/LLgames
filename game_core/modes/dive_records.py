"""Atomic, idempotent salvage receipts and player records."""
import json
import platform
from pathlib import Path


class DiveRecords:
    def __init__(self, path=None):
        self.browser = getattr(platform, 'window', None)
        self.error = False
        self.data = {'discovered': [], 'best': {}}
        self.db = None
        if self.browser is not None:
            self.browser.ttgamesDiveRead()
            return
        import sqlite3
        self.sqlite_error = sqlite3.Error
        self.path = path if path is not None else Path.home() / '.ttgames' / 'modes-v1.sqlite3'
        self.open_native()

    def open_native(self):
        import sqlite3

        try:
            if self.path != ':memory:':
                self.path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(self.path)
            with self.db:
                self.db.executescript("""
                    CREATE TABLE IF NOT EXISTS dive_receipts_v1 (
                        run TEXT, instance TEXT, treasure TEXT, value INTEGER,
                        PRIMARY KEY (run, instance));
                    CREATE TABLE IF NOT EXISTS dive_catalog_v1 (treasure TEXT PRIMARY KEY);
                    CREATE TABLE IF NOT EXISTS dive_best_v1 (sea TEXT PRIMARY KEY, value INTEGER);
                """)
            self.refresh()
        except (OSError, self.sqlite_error):
            self.close()
            self.error = True

    def merge(self, discovered, best):
        self.data['discovered'] = sorted(set(self.data['discovered']).union(discovered))
        for sea, value in best.items():
            self.data['best'][sea] = max(self.data['best'].get(sea, 0), value)

    def refresh(self):
        if self.browser is not None:
            state = json.loads(str(self.browser.ttgamesDiveStatus()))
            self.error = state['error']
            self.merge(state['data']['discovered'], state['data']['best'])
        elif self.db is not None:
            self.merge((row[0] for row in self.db.execute('SELECT treasure FROM dive_catalog_v1')),
                       dict(self.db.execute('SELECT sea,value FROM dive_best_v1')))

    def save(self, dive, retry=False):
        from .deep_dive import TREASURES

        safe = bool(dive.result and dive.result['reason'] == 'safe')
        if not dive.pending and not safe and not retry:
            return
        # Resend all delivered instances so retry can recover an earlier failed write.
        receipts = [(p['instance_id'], p['treasure_id'], TREASURES[p['treasure_id']][2])
                    for p in dive.items.values() if p['state'] == 'delivered']
        dive.pending.clear()
        self.merge((treasure for _,treasure,_ in receipts), {dive.sea:dive.result['income']} if safe else {})
        if retry and self.browser is None and self.db is None:
            self.open_native()
        if self.browser is not None:
            self.browser.ttgamesDiveWrite(json.dumps([dive.run_id, dive.sea, receipts, safe]))
        elif self.db is not None:
            try:
                with self.db:
                    for instance, treasure, value in receipts:
                        self.db.execute('INSERT OR IGNORE INTO dive_receipts_v1 VALUES (?,?,?,?)',
                                        (dive.run_id, instance, treasure, value))
                        self.db.execute('INSERT OR IGNORE INTO dive_catalog_v1 VALUES (?)', (treasure,))
                    if safe:
                        self.db.execute("""
                            INSERT INTO dive_best_v1
                            SELECT ?, COALESCE(SUM(value), 0) FROM dive_receipts_v1 WHERE run = ?
                            ON CONFLICT(sea) DO UPDATE SET value = MAX(value, excluded.value)
                            """, (dive.sea, dive.run_id))
                self.refresh()
                self.error = False
            except self.sqlite_error:
                self.error = True

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None
