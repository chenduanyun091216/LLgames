"""Deep Dive task-book routes, boundary ordering and cross-client receipts."""
from collections import deque
from itertools import combinations
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

from game_core.modes.deep_dive import CONTENT, HZ, TREASURES, Dive, center
from game_core.modes.dive_records import DiveRecords


def junction(edge, room):
    x,y,w,h = edge['rect']
    a,b,r,s = room
    return ((max(x,a)+min(x+w,a+r))/2,(max(y,b)+min(y+h,b+s))/2)


class Route:
    def __init__(self, dive):
        self.dive = dive
        self.room = 'dock'
        self.inputs = []

    def step(self, x=0, y=0, held=(), pressed=(), interact=False):
        args = (x,y,held,pressed,interact)
        self.inputs.append(args)
        self.dive.step(*args)

    def drive(self, point):
        from math import hypot
        for _ in range(1800):
            dx,dy = point[0]-self.dive.x,point[1]-self.dive.y
            length = hypot(dx,dy)
            if length < 2:
                return
            self.step(dx/max(17,length),dy/max(17,length))
        raise AssertionError(f'blocked at {(self.dive.x,self.dive.y)} going to {point} in {self.room}')

    def enter(self, destination):
        d = self.dive
        queue = deque([(self.room,[])])
        seen = {self.room}
        while queue:
            room,path = queue.popleft()
            if room == destination:
                break
            for edge in d.edges:
                if edge['id'] not in d.opened or room not in (edge['a'],edge['b']):
                    continue
                other = edge['b'] if edge['a'] == room else edge['a']
                if other not in seen:
                    queue.append((other,[*path,(edge,room,other)]))
                    seen.add(other)
        else:
            raise AssertionError(f'no open route to {destination}')
        for edge,first,last in path:
            self.drive(junction(edge,d.rooms[first]))
            self.drive(junction(edge,d.rooms[last]))
        self.room = destination

    def acquire(self, item):
        self.enter(item['room'])
        self.drive((item['x'],item['y']))
        if TREASURES[item['treasure_id']][1] > 6:
            for _ in range(60):
                self.step(held=('lift_bag',))
        else:
            self.step(interact=True)

    def home(self):
        self.enter('dock')
        self.drive(center(self.dive.map['dock']))
        for _ in range(15):
            self.step()
        self.step(interact=True)


class DeepDiveTest(unittest.TestCase):
    def test_all_basic_contracts_can_be_driven_and_nine_treasures_persist(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'records.sqlite3'
            records = DiveRecords(path)
            for sea in CONTENT['maps']:
                for tools in combinations(CONTENT['tools'],2):
                    dive = Dive(sea,tools,teaching=True)
                    route = Route(dive)
                    first = next(iter(dive.items.values()))
                    route.acquire(first)
                    route.home()
                    self.assertEqual(dive.result['reason'],'safe')
                    self.assertEqual(dive.result['delivered'],[first['treasure_id']])
                    self.assertTrue(dive.result['complete'])
                    records.save(dive)
                for variant in (0,1):
                    for identifier in ('02','03'):
                        dive = Dive(sea,('sonar','lift_bag'),variant)
                        route = Route(dive)
                        item = dive.items[identifier]
                        route.acquire(item)
                        route.home()
                        self.assertEqual(dive.result['reason'],'safe')
                        self.assertEqual(dive.result['delivered'],[item['treasure_id']])
                        records.save(dive)
            records.close()
            records = DiveRecords(path)
            self.assertEqual(set(records.data['discovered']), set(CONTENT['treasures']))
            self.assertEqual(records.data['best'],{'wreck':130,'grotto':180,'observatory':210})
            records.close()

    def test_cut_resume_short_route_and_unload(self):
        d = Dive('wreck',('cutter','sonar'),0,True)
        route = Route(d)
        route.enter('entry')
        route.drive((1055,480))
        for _ in range(45):
            route.step(held=('cutter',))
        first_oxygen = d.oxygen
        self.assertEqual(d.cut,{'2':45})
        route.drive((910,442))
        route.drive((1055,480))
        for _ in range(75):
            route.step(held=('cutter',))
        self.assertEqual(d.cut,{'2':120})
        self.assertIn('2',d.opened)
        self.assertLess(d.oxygen,first_oxygen-75)
        route.acquire(d.items['03'])
        route.acquire(d.items['02'])
        self.assertIn('超出舱容 1',d.notice)
        self.assertEqual(d.items['02']['state'],'world')
        d.unload('03')
        self.assertEqual(d.items['03']['state'],'world')
        route.acquire(d.items['03'])
        route.home()
        self.assertEqual(d.result['income'],130)

    def test_zero_oxygen_priority_with_idempotent_receipts(self):
        records = DiveRecords(':memory:')
        for seconds, docked, income, reason in ((299,False,0,'oxygen'),
                (300,False,180,'oxygen'),(1,True,180,'safe')):
            dive = Dive('grotto',('lift_bag','sonar'))
            route = Route(dive)
            route.acquire(dive.items['03'])
            self.assertEqual(dive.items['03']['state'],'in_transit')
            if docked:
                for _ in range(300):
                    route.step()
                records.save(dive)
                route.enter('dock')
                route.drive(center(dive.map['dock']))
                for _ in range(15):
                    route.step()
            dive.oxygen = seconds
            for _ in range(seconds-1):
                route.step()
            route.step(interact=docked)
            self.assertEqual((dive.result['income'],dive.result['reason']),(income,reason))
            records.save(dive)
            records.save(dive)
        empty = Dive('wreck',('lift_bag','sonar'))
        empty.oxygen = 1
        empty.step(interact=True)
        self.assertEqual((empty.result['reason'],empty.result['income']),('safe',0))
        self.assertEqual(records.db.execute('SELECT COUNT(*) FROM dive_receipts_v1').fetchone()[0],2)
        self.assertEqual(records.data['best'],{'grotto':180})
        records.close()

    def test_sonar_control_and_failed_write_can_retry(self):
        dive = Dive('wreck',('cutter','sonar'),0,True)
        dive.step(pressed=['sonar'])
        self.assertEqual(dive.oxygen,118*HZ-1)
        self.assertTrue(dive.scanned(dive.x,dive.y))
        for _ in range(180):
            dive.step(held=['sonar'])
        self.assertFalse(dive.scanned(dive.x,dive.y))
        dive.step(pressed=['sonar'])
        self.assertEqual(dive.sonar_at,1)
        dive.step(interact=True)
        records = DiveRecords(':memory:')
        records.db.execute('DROP TABLE dive_best_v1')
        records.save(dive)
        self.assertTrue(records.error)
        self.assertEqual(dive.result['income'],0)
        records.db.execute('CREATE TABLE dive_best_v1 (sea TEXT PRIMARY KEY,value INTEGER)')
        records.save(dive)
        self.assertFalse(records.error)
        self.assertEqual(records.data['best'],{'wreck':0})
        records.close()

    @unittest.skipUnless(shutil.which('node'),'Node is required for independent Phaser parity')
    def test_phaser_replays_first_voyage_and_lift(self):
        if not Path('phaser/src/dive-rules.js').is_file():
            self.skipTest('Local Phaser client is required for parity')
        cases = []
        for sea,item,tools in (('wreck','01',('cutter','sonar')),('grotto','03',('lift_bag','sonar'))):
            dive = Dive(sea,tools,0,True)
            route = Route(dive)
            route.acquire(dive.items[item])
            route.home()
            cases.append([sea,tools,route.inputs,dive.result,dive.tick,[dive.x,dive.y]])
        script = """
            import fs from 'node:fs';
            import assert from 'node:assert/strict';
            import {Dive} from './phaser/src/dive-rules.js';
            const content=JSON.parse(fs.readFileSync('assets/modes/deep_dive/content.json','utf8'));
            for(const [sea,tools,inputs,result,tick,point] of JSON.parse(fs.readFileSync(0,'utf8'))){
                const dive=new Dive(content,sea,tools,0,true,'test');
                for(const input of inputs)dive.step(...input);
                assert.deepEqual(dive.result,result);
                assert.equal(dive.tick,tick);
                assert.ok(Math.hypot(dive.x-point[0],dive.y-point[1])<1e-6);
            }
        """
        completed = subprocess.run(['node','--input-type=module','-e',script],
                                   input=json.dumps(cases),encoding='utf-8',capture_output=True)
        self.assertEqual(completed.returncode,0,completed.stderr)
