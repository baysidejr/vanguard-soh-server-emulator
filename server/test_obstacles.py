"""obstacles.py: blocked()/clear_path() on synthetic obstacle lists (no game files needed)."""
import math
import unittest

import obstacles as O


ROCK = (1000.0, 0.0, 200.0, 0.0, 300.0)       # x, y, radius, z_bottom, z_top
WALL = [(0.0, y, 50.0, 0.0, 500.0) for y in range(-1000, 1001, 100)]


class BlockedTest(unittest.TestCase):
    def test_inside_and_outside(self):
        obs = [ROCK]
        self.assertTrue(O.blocked(obs, 1000, 0, 100))
        self.assertTrue(O.blocked(obs, 1230, 0, 100))      # 230 < 200 + npc radius 40
        self.assertFalse(O.blocked(obs, 1250, 0, 100))
        self.assertFalse(O.blocked(obs, 1250, 0, 100, radius=0))
        self.assertTrue(O.blocked(obs, 1150, 0, 100, radius=0))

    def test_height_range(self):
        obs = [ROCK]
        self.assertFalse(O.blocked(obs, 1000, 0, 400))      # above the top (standing on it)
        self.assertFalse(O.blocked(obs, 1000, 0, -10))      # below (a cave under it)
        self.assertTrue(O.blocked(obs, 1000, 0, 0))
        self.assertTrue(O.blocked(obs, 1000, 0, 300))
        self.assertTrue(O.blocked(obs, 1000, 0))            # z None: ignore height

    def test_empty(self):
        self.assertFalse(O.blocked([], 0, 0, 0))
        self.assertTrue(O.clear_path([], (0, 0, 0), (5000, 5000, 0)))

    def test_grid_index_matches_linear_scan(self):
        obs = [(x * 337.0 % 20000 - 10000, x * 911.0 % 20000 - 10000, 40 + x % 300, 0.0, 400.0)
               for x in range(2000)]
        idx = O.ObstacleList(obs)
        for i in range(500):
            px, py = i * 123.0 % 20000 - 10000, i * 457.0 % 20000 - 10000
            self.assertEqual(O.blocked(obs, px, py, 100), O.blocked(idx, px, py, 100))
            self.assertEqual(sorted(O.hits(obs, px, py, 100)), sorted(O.hits(idx, px, py, 100)))

    def test_grid_handles_big_obstacles(self):
        idx = O.ObstacleList([(5000.0, 5000.0, 2500.0, 0.0, 400.0)])
        self.assertTrue(O.blocked(idx, 5000 - 2400, 5000, 10))
        self.assertTrue(O.blocked(idx, 5000, 5000 + 2500, 10))
        self.assertFalse(O.blocked(idx, 5000, 5000 + 2600, 10))


class ClearPathTest(unittest.TestCase):
    def test_path_through_rock(self):
        obs = O.ObstacleList([ROCK])
        self.assertFalse(O.clear_path(obs, (0, 0, 100), (2000, 0, 100)))
        self.assertTrue(O.clear_path(obs, (0, 500, 100), (2000, 500, 100)))
        self.assertTrue(O.clear_path(obs, (0, 0, 100), (700, 0, 100)))

    def test_path_over_rock(self):
        self.assertTrue(O.clear_path([ROCK], (0, 0, 500), (2000, 0, 500)))

    def test_wall(self):
        self.assertFalse(O.clear_path(WALL, (-500, 0), (500, 0)))
        self.assertFalse(O.clear_path(WALL, (-500, -800), (500, 900)))
        self.assertTrue(O.clear_path(WALL, (-500, 0), (-500, 3000)))
        self.assertTrue(O.clear_path(WALL, (-500, 1200), (500, 1200)))

    def test_thin_obstacle_not_skipped_by_large_step(self):
        obs = [(500.0, 0.0, 10.0, 0.0, 100.0)]
        self.assertFalse(O.clear_path(obs, (0, 0, 50), (1000, 0, 50), step=50, radius=40))

    def test_start_inside_can_leave(self):
        obs = [ROCK]
        self.assertTrue(O.clear_path(obs, (1000, 0, 100), (0, 0, 100)))
        self.assertFalse(O.clear_path(obs, (1000, 0, 100), (0, 0, 100), ignore_start=False))
        # ... but still blocked by a second obstacle on the way out
        obs2 = [ROCK, (500.0, 0.0, 100.0, 0.0, 300.0)]
        self.assertFalse(O.clear_path(obs2, (1000, 0, 100), (0, 0, 100)))

    def test_z_interpolated(self):
        # climbing from below the rock's top to above it: the first half is blocked
        self.assertFalse(O.clear_path([ROCK], (0, 0, 0), (2000, 0, 600)))
        self.assertTrue(O.clear_path([ROCK], (0, 0, 400), (2000, 0, 900)))


class ShapeTest(unittest.TestCase):
    def test_square_box_one_circle(self):
        circles, zb, zt, long_ = O._shapes(O.IDENTITY, (-100, -100, 0), (100, 100, 300))
        self.assertEqual(len(circles), 1)
        self.assertAlmostEqual(circles[0][2], 100)
        self.assertAlmostEqual(zb, 0)
        self.assertAlmostEqual(zt, 300)

    def test_wall_rotated_by_yaw(self):
        # 2000 long along local X, 100 thick; yaw 16384 (90 deg) turns it along world Y
        o = {"Location": (500.0, 0.0, 0.0), "Rotation": (0, 16384, 0), "DrawScale": 2.0}
        circles, zb, zt, long_ = O._shapes(O._actor_xform(o), (-500, -25, 0), (500, 25, 200))
        self.assertGreater(len(circles), 5)
        self.assertAlmostEqual(long_, 1000, places=3)
        for x, y, r in circles:
            self.assertAlmostEqual(x, 500, places=3)
            self.assertAlmostEqual(r, 50, places=3)
            self.assertLessEqual(abs(y), 1000 + 1e-6)
        self.assertAlmostEqual(zt, 400, places=3)

    def test_prefab_composition(self):
        parent = O._actor_xform({"Location": (1000.0, 0.0, 0.0), "Rotation": (0, 16384, 0)})
        child = O._actor_xform({"Location": (100.0, 0.0, 50.0)})
        m, t = O._compose(parent, child)
        self.assertAlmostEqual(t[0], 1000, places=3)
        self.assertAlmostEqual(t[1], 100, places=3)
        self.assertAlmostEqual(t[2], 50, places=3)

    def test_rotation_matrix_orthonormal(self):
        r = O._rot(1234, 40000, -5000)
        for i in range(3):
            col = [r[k][i] for k in range(3)]
            self.assertAlmostEqual(math.sqrt(sum(c * c for c in col)), 1.0, places=9)


if __name__ == "__main__":
    unittest.main()
