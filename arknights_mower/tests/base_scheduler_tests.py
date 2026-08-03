import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import arknights_mower.solvers.base_schedule as base_schedule
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Dormitory, Operator
from arknights_mower.utils.plan import Plan, PlanConfig, PlanTriggerTiming, Room
from arknights_mower.utils.recognize import Scene
from arknights_mower.utils.scheduler_task import TaskTypes, find_next_task

with patch.dict("sys.modules", {"RecruitSolver": MagicMock()}):
    pass


class TestBaseScheduler(unittest.TestCase):
    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_run_order_solver_uses_current_time_for_expired_exhaust_task(self):
        solver = BaseSchedulerSolver()
        solver._training_sm = MagicMock()
        solver._training_sm.is_operator_protected.return_value = False
        solver.tasks = []
        solver.drone_room = None
        solver.op_data = MagicMock()
        solver.op_data.exhaust_agent = ["伊内丝"]
        solver.op_data.rest_in_full_group = set()
        solver.op_data.groups = {}
        solver.op_data.operators = {
            "伊内丝": Operator(
                "伊内丝",
                "meeting",
                group="",
                current_room="meeting",
                current_index=0,
                exhaust_require=True,
                mood=1,
                lower_limit=0,
                operator_type="high",
                depletion_rate=1,
            )
        }
        start_time = datetime(2026, 5, 2, 15, 19, 33)
        detected_exhaust_time = start_time + timedelta(minutes=10)

        class FixedDateTime(datetime):
            now_value = start_time

            @classmethod
            def now(cls, tz=None):
                if tz is not None:
                    return cls.now_value.replace(tzinfo=tz)
                return cls.now_value

        with (
            patch.object(base_schedule, "datetime", FixedDateTime),
            patch.object(BaseSchedulerSolver, "plan_run_order"),
            patch.object(BaseSchedulerSolver, "check_fia", return_value=(None, None)),
            patch.object(BaseSchedulerSolver, "enter_room"),
            patch.object(
                BaseSchedulerSolver,
                "get_agent_from_room",
                return_value=[{"time": detected_exhaust_time}],
            ),
            patch.object(BaseSchedulerSolver, "back"),
        ):
            solver.run_order_solver()

        self.assertEqual(len(solver.tasks), 1)
        self.assertEqual(solver.tasks[0].type, TaskTypes.EXHAUST_OFF)
        self.assertEqual(solver.tasks[0].time, start_time)
        self.assertIsNone(
            find_next_task(solver.tasks, start_time - timedelta(seconds=900))
        )

        solver.error = True
        FixedDateTime.now_value = start_time + timedelta(seconds=1)
        with (
            patch.object(base_schedule, "datetime", FixedDateTime),
            patch.object(BaseSchedulerSolver, "scene", return_value=Scene.INDEX),
        ):
            solver.handle_error(force=True)

        self.assertEqual(len(solver.tasks), 1)
        self.assertEqual(solver.tasks[0].type, TaskTypes.EXHAUST_OFF)

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_backup_plan_solver_Caper(self):
        plan_config = {
            "meeting": [
                Room("伊内丝", "", ["见行者", "陈"]),
                Room("跃跃", "", ["见行者", "陈"]),
            ]
        }
        plan_config1 = {
            "meeting": [
                Room("伊内丝", "", ["陈", "红"]),
                Room("见行者", "", ["陈", "红"]),
            ]
        }
        agent_base_config = PlanConfig("稀音", "稀音", "伺夜")
        plan = {
            # 阶段 1
            "default_plan": Plan(plan_config, agent_base_config),
            "backup_plans": [
                Plan(
                    plan_config1,
                    agent_base_config,
                    trigger=LogicExpression(
                        "op_data.party_time is None", "and", " True "
                    ),
                    task={"meeting": ["Current", "见行者"]},
                )
            ],
        }

        solver = BaseSchedulerSolver()
        solver.global_plan = plan
        solver.initialize_operators()
        solver.tasks = []
        with patch.object(BaseSchedulerSolver, "agent_get_mood") as mock_agent_get_mood:
            mock_agent_get_mood.return_value = None
            solver.backup_plan_solver()
            self.assertEqual(len(solver.tasks), 1)
            solver.party_time = datetime.now()
            solver.backup_plan_solver()
            self.assertTrue(
                all(not condition for condition in solver.op_data.plan_condition)
            )

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_backup_plan_solver_GreyytheLightningbearer(self):
        plan_config = {
            "room_2_3": [Room("雷蛇", "澄闪", ["炎狱炎熔", "格雷伊"])],
            "room_1_3": [Room("承曦格雷伊", "自动化", ["炎狱炎熔"])],
            "room_2_1": [
                Room("温蒂", "自动化", ["泡泡"]),
                Room("森蚺", "自动化", ["火神"]),
                Room("清流", "自动化", ["贝娜"]),
            ],
            "room_2_2": [Room("澄闪", "澄闪", ["炎狱炎熔", "格雷伊"])],
            "central": [
                Room("阿米娅", "", ["诗怀雅"]),
                Room("琴柳", "乌有", ["清道夫"]),
                Room("重岳", "乌有", ["杜宾"]),
                Room("夕", "乌有", ["玛恩纳"]),
                Room("令", "乌有", ["凯尔希"]),
            ],
            "contact": [Room("桑葚", "乌有", ["絮雨"])],
        }
        backup_plan1_config = {
            "central": [
                Room("阿米娅", "", ["诗怀雅"]),
                Room("清道夫", "", ["诗怀雅"]),
                Room("杜宾", "", ["泡泡"]),
                Room("玛恩纳", "", ["火神"]),
                Room("森蚺", "", ["诗怀雅"]),
            ],
            "room_2_1": [
                Room("温蒂", "", ["泡泡"]),
                Room("掠风", "", ["贝娜"]),
                Room("清流", "", ["火神"]),
            ],
            "room_1_3": [Room("Lancet-2", "", ["承曦格雷伊"])],
            "room_2_2": [Room("澄闪", "", ["承曦格雷伊", "格雷伊"])],
            "room_2_3": [Room("雷蛇", "", ["承曦格雷伊", "格雷伊"])],
            "contact": [Room("絮雨", "", ["桑葚"])],
        }
        agent_base_config0 = PlanConfig(
            "稀音,黑键,焰尾,伊内丝",
            "稀音,柏喙,伊内丝",
            "伺夜,帕拉斯,雷蛇,澄闪,红云,乌有,年,远牙,阿米娅,桑葚,截云,掠风",
            ling_xi=2,
            resting_threshold=0.1,
        )
        agent_base_config = PlanConfig(
            "稀音,黑键,焰尾,伊内丝",
            "稀音,柏喙,伊内丝",
            "伺夜,帕拉斯,雷蛇,澄闪,红云,乌有,年,远牙,阿米娅,桑葚,截云",
            ling_xi=2,
            free_blacklist="艾丽妮,但书,龙舌兰",
        )
        plan = {
            # 阶段 1
            "default_plan": Plan(plan_config, agent_base_config),
            "backup_plans": [
                Plan(
                    backup_plan1_config,
                    agent_base_config0,
                    trigger=LogicExpression(
                        "op_data.operators['令'].current_room.startswith('dorm')",
                        "and",
                        LogicExpression(
                            "op_data.operators['温蒂'].current_mood() - op_data.operators['承曦格雷伊'].current_mood()",
                            ">",
                            "4",
                        ),
                    ),
                    task={
                        "dormitory_2": [
                            "Current",
                            "Current",
                            "Current",
                            "Current",
                            "承曦格雷伊",
                        ]
                    },
                )
            ],
        }

        solver = BaseSchedulerSolver()
        solver.global_plan = plan
        solver.initialize_operators()
        solver.tasks = []
        with patch.object(BaseSchedulerSolver, "agent_get_mood") as mock_agent_get_mood:
            mock_agent_get_mood.return_value = None
            solver.op_data.operators["令"].current_room = "dorm"
            solver.op_data.operators["温蒂"].mood = 12
            solver.op_data.operators["承曦格雷伊"].mood = 7
            solver.backup_plan_solver()
            self.assertEqual(len(solver.tasks), 1)
            solver.op_data.operators["承曦格雷伊"].mood = 12
            solver.backup_plan_solver()
            self.assertTrue(
                all(not condition for condition in solver.op_data.plan_condition)
            )

    def _create_backup_refresh_solver(self):
        agent_base_config = PlanConfig("", "", "")
        default_plan = {"meeting": [Room("伊内丝", "", ["陈"])]}
        backup_plan = {"meeting": [Room("见行者", "", ["陈"])]}
        plan = {
            "default_plan": Plan(default_plan, agent_base_config),
            "backup_plans": [
                Plan(
                    backup_plan,
                    agent_base_config,
                    trigger=LogicExpression(
                        "op_data.operators['见行者'].current_room", "==", "meeting"
                    ),
                )
            ],
        }

        solver = BaseSchedulerSolver()
        solver.global_plan = plan
        solver.initialize_operators()
        solver.op_data.add(Operator("见行者", ""))
        solver.tasks = []
        solver._training_sm = MagicMock()

        def read_meeting(room, read_time_index):
            if room == "train":
                return []
            op = solver.op_data.operators["见行者"]
            op.current_room = "meeting"
            op.current_index = 0
            op.mood = 5
            op.time_stamp = datetime.now()
            return [{"agent": "见行者", "mood": 5}]

        return solver, read_meeting

    def _create_no_train_plan_solver(self):
        agent_base_config = PlanConfig("", "", "")
        plan = {
            "default_plan": Plan(
                {"meeting": [Room("伊内丝", "", ["陈"])]},
                agent_base_config,
            ),
            "backup_plans": [],
        }

        solver = BaseSchedulerSolver()
        solver.global_plan = plan
        solver.initialize_operators()
        solver.tasks = []
        solver._training_sm = MagicMock()
        return solver

    def _read_no_train_meeting(self, solver):
        def read_room(room, read_time_index):
            if room == "train":
                self.fail("训练室不应被读取")
            op = solver.op_data.operators["伊内丝"]
            op.current_room = "meeting"
            op.current_index = 0
            op.mood = 5
            op.time_stamp = datetime.now()
            return [{"agent": "伊内丝", "mood": 5}]

        return read_room

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_get_agent_from_room_uses_train_slots_without_train_plan(self):
        solver = self._create_no_train_plan_solver()

        with (
            patch.object(BaseSchedulerSolver, "turn_on_room_detail"),
            patch.object(
                BaseSchedulerSolver,
                "detect_product_complete",
                return_value=False,
            ),
            patch.object(BaseSchedulerSolver, "find", return_value=True),
        ):
            result = solver.get_agent_from_room("train")

        self.assertEqual(len(result), 2)
        self.assertEqual([item["agent"] for item in result], ["", ""])

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_tap_confirm_reuses_first_match_position(self):
        solver = BaseSchedulerSolver()
        solver.task = SchedulerTask(task_type=TaskTypes.SHIFT_ON)
        solver.op_data = MagicMock()
        solver.op_data.run_order_rooms = {}
        solver.recog = MagicMock()
        solver.find = MagicMock(side_effect=[(10, 20), None, None, None])
        solver.sleep = MagicMock()
        solver.tap = MagicMock()
        solver.tap_element = MagicMock()

        solver.tap_confirm("room_1_1")

        solver.tap.assert_called_once_with((10, 20))
        solver.tap_element.assert_not_called()

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_accept_order_reuses_successful_detection_for_save_and_tap(self):
        solver = BaseSchedulerSolver()
        solver.recog = MagicMock(w=1920, h=1080)
        solver.order_reader = MagicMock()
        solver.find = MagicMock(side_effect=[(500, 675), None])
        solver.tap = MagicMock()

        solver.accept_order()

        self.assertEqual(solver.find.call_count, 2)
        solver.recog.save_screencap.assert_called_once_with("run_order")
        solver.order_reader.save.assert_called_once_with(solver.recog.img)
        solver.tap.assert_called_once_with((480.0, 270.0), interval=0.5)

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_accept_order_timeout_does_not_save_or_tap(self):
        solver = BaseSchedulerSolver()
        solver.recog = MagicMock(w=1920, h=1080)
        solver.order_reader = MagicMock()
        solver.find = MagicMock(return_value=None)
        solver.tap = MagicMock()
        solver.sleep = MagicMock()

        solver.accept_order()

        self.assertEqual(solver.find.call_count, 8)
        self.assertEqual(solver.recog.update.call_count, 7)
        solver.recog.save_screencap.assert_not_called()
        solver.order_reader.save.assert_not_called()
        solver.tap.assert_not_called()

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_run_order_with_next_order_timer_collects_and_replans(self):
        solver = BaseSchedulerSolver()
        solver.task = SchedulerTask(task_type=TaskTypes.RUN_ORDER)
        solver.task.adjusted = False
        solver.op_data = MagicMock()
        solver.op_data.run_order_rooms = {"room_1_1": []}
        solver.op_data.get_current_room.return_value = ["CurrentAgent"]
        solver.turn_on_room_detail = MagicMock()
        solver.get_order_remaining_time = MagicMock(return_value=3 * 60 * 60)
        solver.back = MagicMock()
        solver.accept_order = MagicMock()
        solver.reset_room_time = MagicMock()

        with (
            patch.object(
                base_schedule.config.conf.run_order_grandet_mode,
                "buffer_time",
                15,
            ),
            patch.object(base_schedule.config.conf, "run_order_delay", 5),
            patch.object(base_schedule, "send_message"),
        ):
            result = solver.agent_arrange_room(
                {"room_1_1": ["CurrentAgent"]},
                "room_1_1",
                {"room_1_1": ["RunOrderAgent"]},
                skip_enter=True,
            )

        self.assertEqual(result, {})
        solver.back.assert_called_once_with()
        solver.accept_order.assert_called_once_with()
        solver.reset_room_time.assert_called_once_with("room_1_1")

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_infra_main_requests_restart_after_mood_read(self):
        solver = BaseSchedulerSolver()
        solver.task = None
        solver.planned = False
        solver.tasks = []
        solver.restart_after_mood_read = True

        with (
            patch.object(BaseSchedulerSolver, "find", return_value=True),
            patch.object(BaseSchedulerSolver, "no_pending_task", return_value=True),
            patch.object(
                BaseSchedulerSolver,
                "agent_get_mood",
                return_value="self_correction",
            ) as mock_agent_get_mood,
            patch.object(BaseSchedulerSolver, "run_order_solver") as mock_run_order,
            patch.object(BaseSchedulerSolver, "plan_solver") as mock_plan,
        ):
            result = solver.infra_main()

        self.assertEqual(result, "restart_after_mood_read")
        self.assertFalse(solver.restart_after_mood_read)
        mock_agent_get_mood.assert_called_once_with(skip_dorm=True)
        mock_run_order.assert_not_called()
        mock_plan.assert_not_called()

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_agent_get_mood_keeps_self_correction_when_backup_refresh_disabled(self):
        solver, read_meeting = self._create_backup_refresh_solver()

        with (
            patch.object(
                base_schedule.config.conf, "refresh_backup_plan_after_mood", False
            ),
            patch.object(BaseSchedulerSolver, "enter_room"),
            patch.object(
                BaseSchedulerSolver,
                "get_agent_from_room",
                side_effect=read_meeting,
            ),
            patch.object(BaseSchedulerSolver, "back"),
        ):
            result = solver.agent_get_mood(skip_dorm=True)

        self.assertEqual(result, "self_correction")
        self.assertEqual(solver.op_data.plan_condition, [False])
        self.assertEqual(solver.op_data.plan["meeting"][0].agent, "伊内丝")
        self.assertTrue(
            any(task.type == TaskTypes.SELF_CORRECTION for task in solver.tasks)
        )

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_agent_get_mood_does_not_refresh_backup_plan_by_default(self):
        solver, read_meeting = self._create_backup_refresh_solver()

        with (
            patch.object(
                base_schedule.config.conf, "refresh_backup_plan_after_mood", True
            ),
            patch.object(BaseSchedulerSolver, "enter_room"),
            patch.object(
                BaseSchedulerSolver,
                "get_agent_from_room",
                side_effect=read_meeting,
            ),
            patch.object(BaseSchedulerSolver, "back"),
        ):
            result = solver.agent_get_mood(skip_dorm=True)

        self.assertEqual(result, "self_correction")
        self.assertEqual(solver.op_data.plan_condition, [False])
        self.assertEqual(solver.op_data.plan["meeting"][0].agent, "伊内丝")
        self.assertTrue(
            any(task.type == TaskTypes.SELF_CORRECTION for task in solver.tasks)
        )


class TestSchedulerStability(unittest.TestCase):
    def _make_fia_solver(self, grouped):
        now = datetime(2026, 7, 21, 10, 0)
        solver = BaseSchedulerSolver.__new__(BaseSchedulerSolver)
        solver.task = SchedulerTask(time=now)
        group = "test_group" if grouped else ""
        target = Operator(
            "Target",
            "central",
            index=0,
            group=group,
            current_room="dormitory_1",
            current_index=0,
            mood=1,
            upper_limit=24,
            lower_limit=0,
            operator_type="high",
            time_stamp=now,
        )
        other = Operator(
            "Other",
            "room_1_1",
            index=0,
            group=group,
            current_room="room_1_1",
            current_index=0,
            mood=20,
            operator_type="high",
            time_stamp=now,
        )
        solver.op_data = MagicMock()
        solver.op_data.operators = {"Target": target, "Other": other}
        solver.op_data.groups = {group: ["Target", "Other"]} if grouped else {}
        shift = SchedulerTask(
            time=now + timedelta(hours=2),
            task_plan={"central": ["Target"]},
            task_type=TaskTypes.SHIFT_ON,
        )
        solver.tasks = [shift]
        return solver, shift, now

    @patch.object(BaseSchedulerSolver, "check_fia")
    def test_plan_fia_does_not_advance_group_shift_on(self, check_fia):
        solver, shift, now = self._make_fia_solver(grouped=True)
        check_fia.return_value = (["Target"], "dormitory_1")

        with patch.object(base_schedule.config.conf, "fia_fool", True):
            solver.plan_fia()

        self.assertEqual(shift.time, now + timedelta(hours=2))
        self.assertTrue(
            any(task.type == TaskTypes.FIAMMETTA for task in solver.tasks)
        )

    @patch.object(BaseSchedulerSolver, "check_fia")
    def test_plan_fia_still_advances_ungrouped_shift_on(self, check_fia):
        solver, shift, now = self._make_fia_solver(grouped=False)
        check_fia.return_value = (["Target"], "dormitory_1")

        with patch.object(base_schedule.config.conf, "fia_fool", True):
            solver.plan_fia()

        self.assertEqual(shift.time, now + timedelta(seconds=1))
        self.assertTrue(
            any(task.type == TaskTypes.FIAMMETTA for task in solver.tasks)
        )


    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_readiness_retry_scans_dorm_without_arranging(self):
        solver = BaseSchedulerSolver()
        retry = SchedulerTask(
            task_plan={},
            task_type=TaskTypes.NOT_SPECIFIC,
            meta_data="shift_on_readiness_retry:Resting",
        )
        solver.task = retry
        solver.tasks = [retry]
        solver.op_data = MagicMock()
        solver.op_data.operators = {
            "Resting": Operator(
                "Resting",
                "central",
                group="group",
                current_room="",
                current_index=0,
                mood=10,
                operator_type="high",
            )
        }
        solver.op_data.dorm = [
            Dormitory(("dormitory_2", 0), "Resting", None)
        ]
        shift = SchedulerTask(
            time=datetime.now() + timedelta(hours=1),
            task_plan={"central": ["Resting"]},
            task_type=TaskTypes.SHIFT_ON,
        )

        with (
            patch.object(BaseSchedulerSolver, "find", return_value=True),
            patch.object(BaseSchedulerSolver, "enter_room") as enter_room,
            patch.object(BaseSchedulerSolver, "get_agent_from_room") as read_room,
            patch.object(BaseSchedulerSolver, "back") as back,
            patch.object(
                BaseSchedulerSolver,
                "plan_metadata",
                side_effect=lambda: solver.tasks.append(shift),
            ) as replan,
            patch.object(BaseSchedulerSolver, "backup_plan_solver") as backup,
            patch.object(BaseSchedulerSolver, "agent_arrange") as arrange,
        ):
            solver.infra_main()

        enter_room.assert_called_once_with("dormitory_2")
        read_room.assert_called_once_with("dormitory_2")
        back.assert_called_once_with()
        arrange.assert_not_called()
        replan.assert_called_once_with()
        backup.assert_called_once_with(PlanTriggerTiming.AFTER_PLANNING)
        self.assertEqual(solver.tasks, [shift])
        self.assertIsNone(solver.task)

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_readiness_retry_failure_replaces_expired_task_with_future_retry(self):
        solver = BaseSchedulerSolver()
        now = datetime.now()
        retry = SchedulerTask(
            time=now - timedelta(minutes=1),
            task_plan={},
            task_type=TaskTypes.NOT_SPECIFIC,
            meta_data="shift_on_readiness_retry:Resting",
        )
        future_retry = SchedulerTask(
            time=now + timedelta(minutes=10),
            task_plan={},
            task_type=TaskTypes.NOT_SPECIFIC,
            meta_data="shift_on_readiness_retry:Resting",
        )
        solver.task = retry
        solver.tasks = [retry]
        solver.error = False
        solver.op_data = MagicMock()
        solver.op_data.operators = {
            "Resting": Operator(
                "Resting",
                "central",
                group="group",
                current_room="dormitory_2",
                current_index=0,
                mood=10,
                operator_type="high",
            )
        }
        solver.op_data.dorm = [
            Dormitory(("dormitory_2", 0), "Resting", None)
        ]

        with (
            patch.object(BaseSchedulerSolver, "find", return_value=True),
            patch.object(BaseSchedulerSolver, "enter_room"),
            patch.object(
                BaseSchedulerSolver,
                "get_agent_from_room",
                side_effect=RuntimeError("ocr failed"),
            ),
            patch.object(BaseSchedulerSolver, "back") as back,
            patch.object(
                BaseSchedulerSolver,
                "plan_metadata",
                side_effect=lambda: solver.tasks.append(future_retry),
            ) as replan,
        ):
            solver.infra_main()

        back.assert_called_once_with()
        replan.assert_called_once_with()
        self.assertNotIn(retry, solver.tasks)
        self.assertEqual(solver.tasks, [future_retry])
        self.assertGreater(future_retry.time, now)
        self.assertTrue(solver.error)
        self.assertIsNone(solver.task)

    def _make_correction_safety_solver(self, include_ordinary_mismatch):
        now = datetime.now()
        resting = Operator(
            "Resting",
            "central",
            index=0,
            group="group",
            current_room="dormitory_1",
            current_index=0,
            mood=10,
            operator_type="high",
            time_stamp=now,
        )
        unknown = Operator(
            "Unknown",
            "room_1_1",
            index=0,
            group="group",
            current_room="",
            current_index=-1,
            mood=10,
            operator_type="high",
            time_stamp=now,
        )
        operators = {"Resting": resting, "Unknown": unknown}
        plan = {
            "central": [Room("Resting", "group", [])],
            "room_1_1": [Room("Unknown", "group", [])],
        }
        current = {"central": [""], "room_1_1": [""]}
        if include_ordinary_mismatch:
            ordinary = Operator(
                "Expected",
                "meeting",
                index=0,
                current_room="",
                current_index=-1,
                mood=10,
                operator_type="high",
                time_stamp=now,
            )
            operators["Expected"] = ordinary
            plan["meeting"] = [Room("Expected", "", [])]
            current["meeting"] = ["Other"]

        solver = BaseSchedulerSolver.__new__(BaseSchedulerSolver)
        solver.tasks = []
        solver.op_data = MagicMock()
        solver.op_data.operators = operators
        solver.op_data.groups = {"group": ["Resting", "Unknown"]}
        solver.op_data.plan = plan
        solver.op_data.true_exhaust_room = set()
        solver.op_data.get_current_room.side_effect = (
            lambda room, _bypass: current[room]
        )
        return solver

    def test_self_correction_keeps_other_fix_but_blocks_resting_and_unknown_group(self):
        solver = self._make_correction_safety_solver(True)

        result = solver.agent_get_mood(skip_dorm=True)

        self.assertEqual(result, "self_correction")
        self.assertEqual(len(solver.tasks), 1)
        self.assertEqual(solver.tasks[0].type, TaskTypes.SELF_CORRECTION)
        self.assertEqual(solver.tasks[0].plan, {"meeting": ["Expected"]})

    def test_self_correction_is_not_created_when_only_protected_group_remains(self):
        solver = self._make_correction_safety_solver(False)

        result = solver.agent_get_mood(skip_dorm=True)

        self.assertIsNone(result)
        self.assertEqual(solver.tasks, [])

if __name__ == "__main__":
    unittest.main()
