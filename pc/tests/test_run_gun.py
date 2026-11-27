"""Regression checks for the PC, browser and room's shared side-view rules."""
import unittest

import pygame

from game_core.run_gun import RunGun
from online.adapters.run_gun import RunGunRoom


class SideViewTests(unittest.TestCase):
    def test_fixed_turret_warns_then_fires_and_cover_stops_the_round(self):
        game = RunGun()
        world = game.encounter
        turret = world.units[0]
        game.x, game.y = 265, 400
        world.advance([game])
        warning = turret['fire']
        self.assertGreater(warning, world.clock)
        self.assertFalse(world.shots)
        while world.clock < warning:
            world.advance([game])
        self.assertTrue(world.shots)
        self.assertEqual(turret['x'], 465)
        for _ in range(80):
            world.advance([game])
        self.assertFalse(any(b[0] < 350 and abs(b[1]-375)<18 for b in world.shots))

    def test_ground_and_air_shots_obey_eight_directions(self):
        for grounded in (True,False):
            for x,y in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1)):
                with self.subTest(grounded=grounded,x=x,y=y):
                    game=RunGun()
                    game.grounded=grounded
                    game.y=400 if grounded else 240
                    game.keys={pygame.K_j}
                    if x:game.keys.add(pygame.K_a if x<0 else pygame.K_d)
                    if y:game.keys.add(pygame.K_w if y<0 else pygame.K_s)
                    game.step()
                    self.assertEqual(game.aim,(x,y))
                    dx,dy=game.bullets[0][2:4]
                    self.assertAlmostEqual(dx*y-dy*x,0)
                    self.assertGreater(dx*x+dy*y,0)

    def test_lower_core_accepts_standing_horizontal_fire(self):
        game=RunGun(2)
        game.encounter.boss['hp']=0
        game.x,game.y=game.EXIT-115,400
        game.keys={pygame.K_j}
        for _ in range(25):
            game.step()
        self.assertGreater(game.objectives[1],0)

    def test_coop_uses_one_encounter_clock_and_one_boss_health_pool(self):
        room=RunGunRoom()
        room.step()
        first,second=room.actors
        self.assertIs(first.encounter,second.encounter)
        self.assertEqual(first.encounter.clock,1)
        boss=first.encounter.boss
        start=(boss['x']-100,boss['y'])
        first.encounter.hit(start,(boss['x'],boss['y']),3)
        self.assertEqual(room.snapshot()['world']['encounter']['boss']['hp'],boss['max_hp']-3)
