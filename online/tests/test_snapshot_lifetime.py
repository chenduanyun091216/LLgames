"""Snapshots must not retain obsolete worlds until a cyclic GC sweep."""
import gc
import json
import weakref
import unittest

import pygame
from online.adapters.snapshot import encode_world
from online.adapters.presentation import Presentation
from online.tests import test_snapshot_rendering


class SnapshotLifetimeTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        pygame.display.set_mode((960, 720))
        enabled = gc.isenabled()
        gc.collect()
        gc.disable()
        self.addCleanup(gc.enable if enabled else gc.disable)
        self.addCleanup(gc.collect)

    def test_encoding_does_not_keep_world_alive(self):
        class World:
            players = ()
            boss = None
        world = World()
        reference = weakref.ref(world)
        snapshot = encode_world(world)
        del world
        self.assertIsNone(reference())
        self.assertEqual(snapshot['objects'], [])

    def test_replaced_snapshot_releases_removed_visual_objects(self):
        world = test_snapshot_rendering.SnapshotTests().world()
        view = Presentation(pygame.Surface((960, 720)))
        view.apply({'world': json.loads(json.dumps(encode_world(world)))})
        reference = weakref.ref(view.view.bullets[0])
        world.bullets = []
        view.apply({'world': json.loads(json.dumps(encode_world(world)))})
        self.assertIsNone(reference())

    def test_failed_encoding_also_releases_world(self):
        class World:
            players = ()
            boss = None
            skill_flash = object()
        world = World()
        reference = weakref.ref(world)
        try:
            encode_world(world)
        except TypeError:
            pass
        else:
            self.fail('unsupported data must still be rejected')
        del world
        self.assertIsNone(reference())
