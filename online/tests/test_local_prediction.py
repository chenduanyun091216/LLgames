import unittest
from online.client.interpolation import LocalPrediction


class LocalPredictionTests(unittest.TestCase):
    def test_moves_without_waiting_for_snapshot_and_stops_on_release(self):
        p = LocalPrediction()
        p.reconcile((100, 100), -1, 0, 0)
        clamp = lambda xy: xy
        p.advance(0, (0, 0), 300, clamp)
        self.assertEqual(p.advance(1/60, (1, 0), 300, clamp), (105, 100))
        self.assertEqual(p.advance(2/60, (0, 0), 300, clamp), (105, 100))
        self.assertEqual(p.advance(3/60, (-1, 0), 300, clamp), (100, 100))

    def test_acknowledged_history_does_not_pull_continuous_motion_back(self):
        p = LocalPrediction()
        p.reconcile((100, 100), -1, 0, 0)
        p.advance(0, (1, 0), 300, lambda xy: xy)
        p.sent_input(1, 0)
        points = []
        for i in range(1, 120):
            now = i / 60
            if i % 6 == 0:
                # Server acknowledges motion 100 ms behind the local display.
                p.reconcile((100 + (now-.1)*300, 100), 1, (now-.1)*1000, now)
            points.append(p.advance(now, (1, 0), 300, lambda xy: xy)[0])
        self.assertTrue(all(abs(b-a-5) < .001 for a,b in zip(points,points[1:])))
        self.assertLessEqual(len(p.history), 180)

    def test_bounds_teleport_and_long_disconnect(self):
        p = LocalPrediction()
        p.reconcile((100, 100), -1, 0, 0)
        p.sent_input(1, 0)
        clamp = lambda xy: (min(110, max(0, xy[0])), xy[1])
        p.advance(0, (1, 0), 300, clamp)
        self.assertEqual(p.advance(.05, (1, 0), 300, clamp), (110, 100))
        self.assertEqual(p.advance(1, (1, 0), 300, clamp), (110, 100))
        p.reconcile((500, 100), 1, 0, 1)
        self.assertEqual(p.position, (500, 100))
        self.assertEqual(p.correction, (0, 0))

    def test_bidirectional_jitter_with_turn_and_stop(self):
        import heapq
        p = LocalPrediction()
        p.reconcile((300, 100), -1, 0, 0)
        inputs, snapshots = [], []
        seq = 0
        server_x = 300
        server_axis = 0
        accepted_seq = -1
        accepted_at = 0
        sent_last = -1
        last_arrival = 0
        points = []
        for frame in range(300):
            now = frame / 60
            axis = 1 if now < 1 else -1 if now < 2 else 0
            if frame % 3 == 0 or axis != sent_last:
                seq += 1
                p.sent_input(seq, now)
                heapq.heappush(inputs, (now + .04, seq, axis))
                sent_last = axis
            while inputs and inputs[0][0] <= now:
                accepted_at, accepted_seq, server_axis = heapq.heappop(inputs)
            server_x += server_axis * 300 / 60
            if frame % 2 == 0:
                delay = .115 if frame % 60 == 0 else .04
                last_arrival = max(last_arrival, now + delay)
                heapq.heappush(snapshots, (last_arrival, frame, server_x, accepted_seq,
                                           (now-accepted_at)*1000))
            while snapshots and snapshots[0][0] <= now:
                _, _, x, ack, age = heapq.heappop(snapshots)
                p.reconcile((x, 100), ack, age, now)
            points.append(p.advance(now, (axis, 0), 300, lambda xy: xy)[0])
        self.assertGreater(points[1], points[0])
        self.assertLess(points[61], points[60])
        self.assertLess(max(abs(b-a) for a,b in zip(points, points[1:])), 10)
        self.assertAlmostEqual(points[-1], server_x, delta=.1)
        self.assertLess(max(points[150:])-min(points[150:]), 1)
