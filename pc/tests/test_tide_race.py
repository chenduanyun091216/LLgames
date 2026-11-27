from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from game_core.modes.tide_race import COUNTDOWN, LIMIT, Race, TRACK_IDS, wave
from game_core.modes.tide_records import Ghost, RaceRecords, valid_record


def finish(track, dive=False, forward=0):
    race = Race(track)
    while not race.result:
        race.step({1: (forward, 0, 2 if dive else 0)})
    return race


def place_at_finish(race, slot):
    r = race.racers[slot]
    r.x = race.track['length'] - 1
    r.y = wave(race.track, r.x, race.clock)[0]
    r.gates = [COUNTDOWN+100, COUNTDOWN+200, COUNTDOWN+300]
    r.joined = True


class TideRaceTests(unittest.TestCase):
    def test_three_teaching_waves(self):
        def run(coach):
            race = Race()
            lesson = race.track['training']
            lands = []
            while race.racers[1].x < lesson['section_end']:
                tick = race.clock + 1
                held = any(j+lesson['fold_delay'] <= tick <= end for j,end in zip(lesson['launch'],lesson['land']))
                old = race.racers[1].combo
                race.step({1: (1,0,2 if coach and held else 0)}, (1,) if coach and tick in lesson['launch'] else ())
                if race.racers[1].combo > old:
                    lands.append(race.clock)
            return race, lands
        base, _ = run(False)
        trained, lands = run(True)
        self.assertEqual(lands, trained.track['training']['land'])
        self.assertEqual(trained.racers[1].combo, 3)
        self.assertLess(trained.clock, base.clock)

    def test_every_track_finishes_on_both_routes(self):
        ranges = [(85,115),(100,140),(120,165)]
        for track, (lo, hi) in zip(TRACK_IDS, ranges):
            with self.subTest(track=track):
                surface, under = finish(track), finish(track, dive=True)
                self.assertTrue(lo*60 <= surface.clock <= hi*60)
                self.assertLess(under.clock, surface.clock)
                r = under.racers[1]
                self.assertEqual((r.branch,r.route,len(r.gates)), ('surface','deep',3))
                self.assertTrue(r.joined and valid_record(under.track, under.clock, under.samples))

    def test_checkpoint_does_not_count_gate_twice(self):
        race = Race()
        race.track = deepcopy(race.track)
        start = race.track['branch'][0]
        race.track['gates'] = [start+100, *race.track['gates'][1:]]
        race.track['obstacles'].insert(0,['deep',start+104,310,12,150])
        while race.racers[1].pose != 'reset' and race.clock<3000:
            race.step({1:(1,0,2)})
        r = race.racers[1]
        self.assertEqual((r.branch,r.pose,r.freeze), ('deep','reset',24))
        saved = r.gates[0]
        self.assertLess(r.x,race.track['gates'][0])
        self.assertIn([race.clock, round(r.x),round(r.y),'reset','deep'], race.samples)
        clock = race.clock
        race.track['obstacles'].pop(0)
        for _ in range(24):
            race.step({1:(1,1,2)}, (1,))
        self.assertEqual(race.clock,clock+24)
        self.assertEqual(r.freeze,0)
        while r.x < start+115:
            race.step({1:(1,0,2)})
        self.assertEqual(r.gates,[saved])

    def test_boundary_of_launch_cache_and_green_light(self):
        race = Race()
        for _ in range(COUNTDOWN):
            race.step({1:(1,0,0)}, (1,))
        r = race.racers[1]
        self.assertEqual((r.x,r.pose,r.launch_until),(0,'swim',-1))
        for _ in range(7):
            race.step({1:(1,0,0)}, (1,) if not _ else ())
        self.assertEqual(r.pose,'glide')
        self.assertGreater(r.x,0)
        for _ in range(120):
            race.step()
        self.assertEqual(r.pose,'swim')

    def test_atomic_best_version_and_ghost_discontinuities(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'race.sqlite3'
            race = Race()
            records = RaceRecords(race, path)
            for tick in (6120, 6480, 5940):
                sim = Race()
                sim.tick = COUNTDOWN + tick
                sim.racers[1].finish_tick = sim.tick
                sim.result = sim.ranking()
                sim.samples = [[0,0,276,'swim','surface'],[tick,race.track['length'],276,'swim','surface']]
                records.save(sim)
            records.close()
            reopened = RaceRecords(race,path)
            self.assertEqual(reopened.best[0],5940)
            self.assertEqual(reopened.best[1][-1][0],5940)
            reopened.close()
            race.track = dict(race.track,version=2)
            update = RaceRecords(race,path)
            self.assertIsNone(update.best)
            update.close()
            run = finish('lighthouse')
            session = {}
            failed = RaceRecords(run, Path(temp), session=session)
            failed.save(run)
            self.assertTrue(failed.error)
            self.assertEqual(failed.best[0],run.clock)
            self.assertEqual(RaceRecords(run, Path(temp), session=session).best,failed.best)
        replay = Ghost([[0,0,276,'swim','surface'],[6,18,280,'swim','surface'],
                        [8,20,360,'dive','deep'],[11,17,390,'reset','deep']])
        self.assertEqual(replay.at(3)[:2],[9,278])
        self.assertEqual(replay.at(7),[18,280,'swim','surface'])
        self.assertEqual(replay.at(10),[20,360,'dive','deep'])
        self.assertEqual(replay.at(11),[17,390,'reset','deep'])

    def test_inclusive_deadline_and_leave_after_finish(self):
        for last_tick in (7200,None):
            race = Race(slots=(1,2))
            race.tick = 5999
            place_at_finish(race,1)
            race.step()
            self.assertEqual(race.racers[1].finish_tick,6000)
            race.step(departures=(1,))
            self.assertIsNone(race.result)
            self.assertEqual(race.deadline_tick,7200)
            race.tick = 7199
            if last_tick:
                place_at_finish(race,2)
            race.step()
            self.assertEqual(race.racers[2].finish_tick,last_tick)
            self.assertEqual([r['rank'] for r in race.result],[1,2])

    def test_tie_timeout_and_forfeit(self):
        race = Race(slots=(1,2))
        race.tick = 5999
        for slot in (1,2):
            place_at_finish(race,slot)
        race.step(departures=(1,))
        self.assertEqual([r['rank'] for r in race.result],[1,1])
        race = Race(slots=(1,2))
        race.tick = COUNTDOWN+LIMIT-1
        race.racers[2].gates.append(501)
        race.step()
        self.assertEqual([(r['slot'],r['status']) for r in race.result],[(2,'timeout'),(1,'timeout')])
        race = Race(slots=(1,2))
        race.depart((1,))
        self.assertEqual(race.result[0]['status'],'won_by_forfeit')
        self.assertEqual(race.result[1]['status'],'departed')
