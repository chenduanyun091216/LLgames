"""Room orientation is independent of visibility, connection and shop pauses."""
import json
import unittest
from online.shared.protocol import decode, ProtocolError
from online.server.app import Room, Peer
from online.tests.test_server import FakeGame

class OrientationTests(unittest.TestCase):
    def room(self):
        r=Room(FakeGame)
        r.players=[Peer(1,ws=object(),ready=True),Peer(2,ws=object(),ready=True)]
        return r
    def report(self,r,slot,orientation):
        return r.handle(r.players[slot-1],dict(type='orientation',orientation=orientation))
    def choose(self,r,orientation):
        return r.handle(r.players[0],dict(type='room_orientation',orientation=orientation))
    def test_strict_protocol(self):
        for kind in ('orientation','room_orientation'):
            for v in ('portrait','landscape'):
                decode(json.dumps(dict(type=kind,orientation=v)))
            for v in (None,True,0,{},[], 'auto','LANDSCAPE'):
                with self.assertRaises(ProtocolError):
                    decode(json.dumps(dict(type=kind,orientation=v)))
            for key in ('slot','world_size','width','paused','ready'):
                with self.assertRaises(ProtocolError):
                    decode(json.dumps(dict(type=kind,orientation='portrait',**{key:1})))
    def test_host_selection_and_start_gate(self):
        r=self.room()
        self.assertEqual(r.handle(r.players[1],dict(type='room_orientation',orientation='portrait')),'host_only')
        self.choose(r,'portrait')
        self.assertFalse(any(p.ready for p in r.players))
        for p in r.players:p.ready=True
        start=dict(type='start',difficulty='medium')
        self.assertEqual(r.handle(r.players[0],start),'orientation_mismatch')
        self.report(r,1,'portrait');self.report(r,2,'landscape')
        self.assertEqual(r.handle(r.players[0],start),'orientation_mismatch')
        self.report(r,2,'portrait')
        self.assertIsNone(r.handle(r.players[0],start))
        self.assertEqual(r.snapshot()['world_size'],[480,720])
        self.assertEqual(self.choose(r,'landscape'),'match_in_progress')
    def test_rotation_clears_input_preserves_other_pauses(self):
        r=self.room();self.choose(r,'landscape')
        for p in r.players:p.ready=True;p.orientation='landscape'
        r.start('medium');r.game.set_input(1,1,0,True)
        self.report(r,2,'portrait')
        self.assertEqual(r.pause_reason(),'orientation_mismatch')
        self.assertTrue(all(v==(0,0,False) for v in r.game.inputs.values()))
        self.assertEqual(r.handle(r.players[0],dict(type='input',match_id=r.match_id,seq=1,dx=1,dy=0,shoot=True)),'paused')
        r.players[0].suspended=True;self.report(r,2,'landscape')
        self.assertEqual(r.pause_reason(),'suspended')
        r.players[0].suspended=False;r.players[1].ws=None
        self.assertEqual(r.pause_reason(),'disconnected')
        r.players[1].ws=object();r.players[1].orientation=None
        self.assertEqual(r.pause_reason(),'orientation_mismatch')
        self.report(r,2,'landscape');self.assertIsNone(r.pause_reason())
        original=r.game.snapshot
        r.game.snapshot=lambda:dict(original(),paused=True,pause_reason='shop')
        self.report(r,1,'portrait');self.report(r,1,'landscape')
        self.assertEqual(r.snapshot()['pause_reason'],'shop')
