import datetime
import json
import time
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


class TestDormOrderProtection(unittest.TestCase):
    def setUp(self):
        self.previous_conf = config.conf
        self.previous_plan = config.plan
        self.previous_token = getattr(server.app, "token", None)
        server.app.token = "test-token"
        self.client = server.app.test_client()

    def tearDown(self):
        config.conf = self.previous_conf
        config.plan = self.previous_plan
        if self.previous_token is None:
            delattr(server.app, "token")
        else:
            server.app.token = self.previous_token

    @staticmethod
    def make_plan(second_room_free=True):
        dormitory_2 = {
            "name": "dormitory_2",
            "plans": [{"agent": "Free" if second_room_free else "Resident"}],
        }
        return config.PlanModel(
            plan1={
                "dormitory_1": {
                    "name": "dormitory_1",
                    "plans": [
                        {"agent": "Manager"},
                        {"agent": "Free"},
                        {"agent": "Free"},
                    ],
                },
                "dormitory_2": dormitory_2,
            }
        )

    def test_valid_custom_order_is_preserved(self):
        plan = self.make_plan()
        requested = "dormitory_1_2,dormitory_2_0,dormitory_1_1"

        self.assertEqual(
            server._reconcile_dorm_order(plan, requested),
            requested,
        )

    def test_empty_conf_post_rebuilds_order_from_current_plan(self):
        config.plan = self.make_plan()
        config.conf.dorm_order = (
            "dormitory_1_2,dormitory_2_0,dormitory_1_1"
        )
        payload = config.conf.model_dump()
        payload["dorm_order"] = ""

        with patch.object(config, "save_conf"):
            response = self.client.post(
                "/conf",
                json=payload,
                headers={"token": "test-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            config.conf.dorm_order,
            "dormitory_1_2,dormitory_2_0,dormitory_1_1",
        )

    def test_plan_topology_change_rebuilds_stale_order(self):
        config.plan = self.make_plan()
        config.conf.dorm_order = (
            "dormitory_1_1,dormitory_2_0,dormitory_1_2"
        )
        new_plan = self.make_plan(second_room_free=False)

        with (
            patch.object(config, "save_plan") as save_plan,
            patch.object(config, "save_conf") as save_conf,
        ):
            server._save_plan_with_dorm_order(new_plan)

        self.assertEqual(
            config.conf.dorm_order,
            "dormitory_1_1,dormitory_1_2",
        )
        save_plan.assert_called_once()
        save_conf.assert_called_once()


class TestWebSocketLogBroadcast(unittest.TestCase):
    def setUp(self):
        self.previous_connections = server.ws_connections
        self.previous_log_lines = server.log_lines
        server.ws_connections = []
        server.log_lines = []

    def tearDown(self):
        server.ws_connections = self.previous_connections
        server.log_lines = self.previous_log_lines

    def test_log_reader_consumes_messages_after_server_startup(self):
        config.log_queue.put("startup-probe")

        for _ in range(100):
            if "startup-probe" in server.log_lines:
                break
            time.sleep(0.01)

        self.assertIn("startup-probe", server.log_lines)

    def test_failed_connection_does_not_block_other_clients(self):
        failed = MagicMock()
        failed.send.side_effect = RuntimeError("connection closed")
        healthy = MagicMock()
        server.ws_connections.extend([failed, healthy])

        with patch.object(server, "get_latest_screenshot", return_value=""):
            server._broadcast_log("hello")

        healthy.send.assert_called_once()
        payload = json.loads(healthy.send.call_args.args[0])
        self.assertEqual(payload["type"], "log")
        self.assertEqual(payload["data"], "hello")
        self.assertNotIn(failed, server.ws_connections)
        self.assertIn(healthy, server.ws_connections)


if __name__ == "__main__":
    unittest.main()
