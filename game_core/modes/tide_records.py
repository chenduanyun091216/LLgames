"""Versioned personal best and replay, stored as a single record."""
from bisect import bisect_right
import json
from pathlib import Path
import platform

from .tide_race import LIMIT


def valid_record(track, ticks, samples):
    if type(ticks) is not int or not 0 < ticks <= LIMIT or not isinstance(samples, list) or not samples:
        return False
    previous = -1
    for row in samples:
        if not isinstance(row, list) or len(row) != 5:
            return False
        t, x, y, pose, branch = row
        if (any(type(n) is not int for n in (t, x, y)) or not previous < t <= ticks
                or not 0 <= x <= track['length'] or not 0 <= y <= 540
                or pose not in ('swim', 'glide', 'dive', 'reset') or branch not in ('surface', 'deep')):
            return False
        previous = t
    return (samples[0][0:2] == [0, 0] and samples[-1][0:2] == [ticks, track['length']]
            and samples[-1][-1] == 'surface')


class Ghost:
    def __init__(self, samples):
        self.samples = samples
        self.ticks = [row[0] for row in samples]

    def at(self, tick):
        if tick > self.ticks[-1]:
            return None
        index = bisect_right(self.ticks, tick)
        a = self.samples[max(0, index-1)]
        if index >= len(self.samples):
            return a[1:]
        b = self.samples[index]
        if a[4] != b[4] or b[3] == 'reset':
            return a[1:]
        weight = (tick-a[0])/(b[0]-a[0])
        return [a[i]+(b[i]-a[i])*weight for i in (1, 2)] + a[3:]


class RaceRecords:
    def __init__(self, race, path=None, *, session=None):
        self.track = race.track
        self.key = (race.track_id, race.track['version'], race.rules_version)
        self.browser_key = json.dumps(self.key)
        self.revision = -1
        self.session = session if session is not None else {}
        self.best = self.session.get(self.key)
        self.error = False
        self.browser = getattr(platform, 'window', None)
        self.db = None
        if self.browser is not None:
            self.browser.ttgamesRaceRead(self.browser_key, self.track['length'])
            return
        import sqlite3
        self.sqlite_error = sqlite3.Error
        path = path if path is not None else Path.home() / '.ttgames' / 'modes-v1.sqlite3'
        try:
            if path != ':memory:':
                path = Path(path)
                path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(path)
            with self.db:
                self.db.execute("""
                    CREATE TABLE IF NOT EXISTS tide_best_v1 (
                    track TEXT, track_version INTEGER, rules_version INTEGER, ticks INTEGER, samples TEXT,
                    PRIMARY KEY(track, track_version, rules_version))
                """)
            self.refresh()
        except (OSError, self.sqlite_error):
            self.error = True

    def accept(self, ticks, samples):
        if valid_record(self.track, ticks, samples):
            if self.best is None or ticks < self.best[0]:
                self.best = (ticks, samples)
                self.session[self.key] = self.best
        else:
            self.error = True

    def refresh(self):
        if self.browser is not None:
            revision = self.browser.ttgamesRaceRevision(self.browser_key)
            if revision == self.revision:
                return
            self.revision = revision
            status = json.loads(str(self.browser.ttgamesRaceStatus(self.browser_key)))
            self.error = status['error']
            if status['best'] and (self.best is None or status['best'][0] < self.best[0]):
                self.accept(*status['best'])
        elif self.db is not None:
            try:
                row = self.db.execute('SELECT ticks, samples FROM tide_best_v1 WHERE track=? AND track_version=? AND rules_version=?',
                                      self.key).fetchone()
                if row:
                    self.accept(row[0], json.loads(row[1]))
            except (self.sqlite_error, ValueError):
                self.error = True

    def save(self, race):
        if race.result is None or len(race.racers) != 1 or race.racers[1].finish_tick is None:
            return
        ticks, samples = race.racers[1].finish_tick-race.start_tick, race.samples
        if not valid_record(self.track, ticks, samples):
            self.error = True
            return
        self.accept(ticks, samples)
        if self.browser is not None:
            self.browser.ttgamesRaceWrite(json.dumps([self.key, ticks, samples]), self.track['length'])
        elif self.db is not None:
            try:
                with self.db:
                    self.db.execute("""
                        INSERT INTO tide_best_v1 VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(track, track_version, rules_version) DO UPDATE SET
                            ticks=excluded.ticks, samples=excluded.samples
                        WHERE excluded.ticks < tide_best_v1.ticks
                    """, (*self.key, ticks, json.dumps(samples, separators=(',', ':'))))
                self.error = False
                self.refresh()
            except self.sqlite_error:
                self.error = True

    def close(self):
        if self.db is not None:
            self.db.close()
