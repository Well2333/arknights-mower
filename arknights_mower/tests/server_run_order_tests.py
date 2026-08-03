import datetime
import unittest
from unittest.mock import MagicMock, patch

import arknights_mower.__main__ as mower_main
import server
from arknights_mower.utils import config
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


class TestImmediateRunOrderEndpoint(unittest.TestCase):
    def setUp(self):
        config.wake_mower.clear()
        self.previous_token = getattr(server.app, "token", None)
        server.app.token = "test-token"
        self.client = server.app.test_client()

    def tearDown(self):
        config.wake_mower.clear()
        if self.previous_token is None:
            delattr(server.app, "token")
        else:
            server.app.token = self.previous_token

    def post_immediate(self):
        return self.client.post(
            "/run-order/immediate",
            headers={"token": "test-token"},
        )

    def test_sleeping_scheduler_moves_nearest_run_order_and_wakes(self):
        now = datetime.datetime.now()
        other = SchedulerTask(
            time=now + datetime.timedelta(minutes=5),
            task_type=TaskTypes.SHIFT_ON,
        )
        target = SchedulerTask(
            time=now + datetime.timedelta(minutes=10),
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room_1_1",
        )
        original_other_time = other.time
        scheduler = MagicMock(
            sleeping=True,
            task=None,
            tasks=[other, target],
        )
        mower_thread = MagicMock()
        mower_thread.is_alive.return_value = True

        with (
            patch.object(mower_main, "base_scheduler", scheduler),
            patch.object(server, "mower_thread", mower_thread),
        ):
            response = self.post_immediate()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        self.assertTrue(target.immediate)
        self.assertLessEqual(target.time, datetime.datetime.now())
        self.assertEqual(other.time, original_other_time)
        self.assertTrue(config.wake_mower.is_set())

    def test_running_scheduler_defers_only_target_until_batch_end(self):
        now = datetime.datetime.now()
        active = SchedulerTask(
            time=now,
            task_type=TaskTypes.SHIFT_ON,
        )
        following = SchedulerTask(
            time=now + datetime.timedelta(minutes=1),
            task_type=TaskTypes.WORKSHOP,
        )
        target = SchedulerTask(
            time=now + datetime.timedelta(minutes=20),
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room_1_1",
        )
        original_active_time = active.time
        original_following_time = following.time
        scheduler = MagicMock(
            sleeping=False,
            task=active,
            tasks=[active, following, target],
        )
        mower_thread = MagicMock()
        mower_thread.is_alive.return_value = True

        with (
            patch.object(mower_main, "base_scheduler", scheduler),
            patch.object(server, "mower_thread", mower_thread),
            patch.object(config.conf, "run_order_delay", 3),
        ):
            response = self.post_immediate()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        self.assertTrue(target.immediate)
        self.assertEqual(
            target.time,
            following.time + datetime.timedelta(seconds=1),
        )
        self.assertEqual(active.time, original_active_time)
        self.assertEqual(following.time, original_following_time)
        self.assertFalse(config.wake_mower.is_set())


if __name__ == "__main__":
    unittest.main()
