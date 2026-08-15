import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import arknights_mower.solvers.base_schedule as base_schedule
import arknights_mower.solvers.base_mixin as base_mixin
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Dormitory, Operator, Operators
from arknights_mower.utils.plan import Plan, PlanConfig, PlanTriggerTiming, Room
from arknights_mower.utils.recognize import Scene
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    find_next_task,
)

with patch.dict("sys.modules", {"RecruitSolver": MagicMock()}):
    pass


class TestBaseScheduler(unittest.TestCase):
    def test_backup_validation_checks_disjoint_plans_together(self):
        operators = Operators.__new__(Operators)
        operators.run_order_rooms = {"room_1_1": {}, "room_2_1": {}}
        first = MagicMock()
        first.plan = {"room_1_1": [Room("芬", "", ["香草"])]}
        second = MagicMock()
        second.plan = {"room_2_1": [Room("克洛丝", "", ["安比尔"])]}
        operators.backup_plans = [first, second]

        def validate(condition, refresh):
            if condition == [True, True]:
                return "组合状态冲突"
            return None

        operators.swap_plan = MagicMock(side_effect=validate)

        result = operators.validate_backup_plans()

        self.assertFalse(result["success"])
        self.assertIn("组合状态冲突", result["message"])
        operators.swap_plan.assert_any_call([True, True], True)

    def test_backup_validation_rejects_lost_run_order_room(self):
        operators = Operators.__new__(Operators)
        operators.run_order_rooms = {}
        backup = MagicMock()
        backup.plan = {"room_2_1": [Room("芬", "", ["香草"])]}
        operators.backup_plans = [backup]

        def validate(condition, refresh):
            operators.run_order_rooms = (
                {"room_1_1": {}, "room_2_1": {}}
                if condition == [False]
                else {"room_1_1": {}}
            )
            return None

        operators.swap_plan = MagicMock(side_effect=validate)

        result = operators.validate_backup_plans()

        self.assertFalse(result["success"])
        self.assertIn("跑单房间在副表组合中发生变化", result["message"])

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_verify_agent_recovers_after_transient_mismatch(self):
        solver = BaseSchedulerSolver()
        solver.recog = MagicMock()
        solver.find = MagicMock(return_value=None)

        with patch.object(
            base_mixin,
            "operator_list",
            side_effect=[[["错误干员", None]], [["目标干员", None]]],
        ) as recognize:
            result = solver.verify_agent(["目标干员"], "dormitory_1")

        self.assertTrue(result)
        self.assertEqual(recognize.call_count, 2)
        solver.recog.update.assert_called_once_with()

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_verify_agent_rejects_persistent_mismatch_or_empty_result(self):
        solver = BaseSchedulerSolver()
        solver.recog = MagicMock()
        solver.find = MagicMock(return_value=None)

        with patch.object(
            base_mixin,
            "operator_list",
            side_effect=[[["错误干员", None]], [], [["错误干员", None]]],
        ) as recognize:
            result = solver.verify_agent(["目标干员"], "dormitory_1")

        self.assertFalse(result)
        self.assertEqual(recognize.call_count, 3)
        self.assertEqual(solver.recog.update.call_count, 2)

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
            solver.tasks = []
            solver.party_time = datetime.now()
            self.assertTrue(solver.backup_plan_solver())
            self.assertTrue(
                all(not condition for condition in solver.op_data.plan_condition)
            )
            self.assertEqual(len(solver.tasks), 1)
            self.assertEqual(
                solver.tasks[0].plan,
                {"meeting": ["Current", "跃跃"]},
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
    def test_immediate_run_order_long_timer_reaches_arrangement(self):
        solver = BaseSchedulerSolver()
        solver.task = SchedulerTask(
            task_type=TaskTypes.RUN_ORDER,
            immediate=True,
            meta_data="room_1_1",
        )
        solver.op_data = MagicMock()
        solver.op_data.run_order_rooms = {"room_1_1": []}
        solver.op_data.get_current_room.return_value = ["CurrentAgent"]
        solver.turn_on_room_detail = MagicMock()
        solver.get_order_remaining_time = MagicMock(return_value=1088)
        solver.back = MagicMock()
        solver.accept_order = MagicMock()
        solver.reset_room_time = MagicMock()
        solver.find = MagicMock(return_value=(100, 100))
        solver.choose_agent = MagicMock()
        solver.tap_confirm = MagicMock()
        solver.get_agent_from_room = MagicMock(
            return_value=[{"agent": "RunOrderAgent"}]
        )
        solver.scene = MagicMock(return_value=Scene.INFRA_MAIN)
        solver.waiting_scene = set()

        with (
            patch.object(
                base_schedule.config.conf.run_order_grandet_mode,
                "buffer_time",
                180,
            ),
            patch.object(base_schedule.config.conf, "run_order_delay", 8),
            patch.object(base_schedule, "send_message") as mock_send_message,
        ):
            result = solver.agent_arrange_room(
                {"room_1_1": ["CurrentAgent"]},
                "room_1_1",
                {"room_1_1": ["RunOrderAgent"]},
                skip_enter=True,
            )

        self.assertEqual(result, {"room_1_1": ["CurrentAgent"]})
        solver.choose_agent.assert_called_once_with(
            ["RunOrderAgent"], "room_1_1", True
        )
        solver.accept_order.assert_not_called()
        solver.reset_room_time.assert_not_called()
        mock_send_message.assert_not_called()

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_immediate_run_order_forces_drone_for_trade_room(self):
        solver = BaseSchedulerSolver()
        solver.task = SchedulerTask(
            task_type=TaskTypes.RUN_ORDER,
            immediate=True,
            meta_data="room_1_1",
        )
        solver.tasks = []
        solver.find = MagicMock(return_value=None)
        solver.op_data = MagicMock()
        solver.op_data.run_order_rooms = {"room_1_1": []}
        solver.op_data.plan = {"room_1_1": []}
        arranged = {"room_1_1": ["Current"]}

        with (
            patch.object(
                BaseSchedulerSolver,
                "agent_arrange_room",
                return_value=arranged,
            ),
            patch.object(BaseSchedulerSolver, "drone") as mock_drone,
            patch.object(
                base_schedule.config.conf.run_order_grandet_mode,
                "buffer_time",
                1,
            ),
        ):
            solver.agent_arrange(
                {
                    "room_1_1": ["Current"],
                    "dormitory_1": ["Current"],
                }
            )

        mock_drone.assert_called_once_with("room_1_1", not_customize=True)

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_immediate_run_order_skips_confirmation_wait(self):
        solver = BaseSchedulerSolver()
        solver.task = SchedulerTask(task_type=TaskTypes.RUN_ORDER, immediate=True)
        solver.op_data = MagicMock()
        solver.op_data.run_order_rooms = {"room_1_1": []}
        solver.recog = MagicMock()
        solver.find = MagicMock(return_value=None)
        solver.sleep = MagicMock()

        with (
            patch.object(
                base_schedule.config.conf.run_order_grandet_mode,
                "buffer_time",
                15,
            ),
            patch.object(base_schedule.config.conf, "run_order_delay", 3),
        ):
            solver.tap_confirm("room_1_1", {"room_1_1": ["Current"]})

        solver.sleep.assert_not_called()

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_idle_sleep_wake_event_reselects_task_and_clears_state(self):
        solver = BaseSchedulerSolver()
        solver.sleeping = False
        solver.recog = MagicMock()
        base_schedule.config.wake_mower.set()

        woke = solver._idle_sleep(30)

        self.assertTrue(woke)
        self.assertFalse(solver.sleeping)
        self.assertFalse(base_schedule.config.wake_mower.is_set())
        solver.recog.update.assert_called_once_with()

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

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_plan_solver_leaves_pending_mastery_to_mastery_sync(self):
        solver = BaseSchedulerSolver()
        solver.op_data = MagicMock()
        solver.op_data.operators = {}
        solver.op_data.print.return_value = ""
        solver.tasks = []
        solver.find_next_task = MagicMock(return_value=None)
        solver.plan_metadata = MagicMock()
        solver.resting = MagicMock(return_value={})
        solver.agent_get_mood = MagicMock(return_value="noop")
        solver.backup_plan_solver = MagicMock()

        with (
            patch.object(base_schedule, "try_reorder", return_value={}),
            patch.object(base_schedule, "try_workshop_tasks"),
            patch.object(base_schedule, "try_add_release_dorm"),
            patch(
                "arknights_mower.utils.mastery_db.get_pending_plans",
                return_value=[{"char_id": "char_test", "skill_index": 1}],
            ) as mock_get_pending,
            patch(
                "arknights_mower.utils.mastery_db.has_in_progress_plan",
                return_value=False,
            ) as mock_has_in_progress,
        ):
            solver.plan_solver()

        self.assertFalse(
            any(task.type == TaskTypes.SKILL_UPGRADE for task in solver.tasks)
        )
        mock_get_pending.assert_not_called()
        mock_has_in_progress.assert_not_called()
        solver.backup_plan_solver.assert_not_called()


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

    def test_self_correction_accepts_replacement_for_off_duty_ungrouped_high(self):
        now = datetime.now()
        ash = Operator(
            "灰烬",
            "room_2_2",
            index=1,
            replacement=["赤刃明霄陈"],
            current_room="",
            current_index=-1,
            mood=9.523,
            operator_type="high",
            time_stamp=now,
        )
        chen = Operator(
            "赤刃明霄陈",
            "",
            current_room="room_2_2",
            current_index=1,
            mood=24,
            operator_type="low",
            time_stamp=now,
        )
        solver = BaseSchedulerSolver.__new__(BaseSchedulerSolver)
        solver.tasks = []
        solver.op_data = MagicMock()
        solver.op_data.operators = {"灰烬": ash, "赤刃明霄陈": chen}
        solver.op_data.groups = {}
        solver.op_data.plan = {
            "room_2_2": [
                Room("凯尔希", "", ["荒芜拉普兰德", "多萝西"]),
                Room("灰烬", "", ["赤刃明霄陈"]),
            ]
        }
        solver.op_data.true_exhaust_room = set()
        solver.op_data.get_current_room.return_value = ["多萝西", "赤刃明霄陈"]

        result = solver.agent_get_mood(skip_dorm=True)

        self.assertIsNone(result)
        self.assertEqual(solver.tasks, [])

class TestMasteryAndDroneHardening(unittest.TestCase):
    def test_mastery_sync_twice_keeps_one_refresh_and_local_expiry(self):
        from arknights_mower.utils import mastery_sync
        from arknights_mower.utils.mastery_sync import MasterySync

        scheduler = MagicMock()
        scheduler.tasks = []
        plan = {
            "char_id": "char_test",
            "skill_index": 1,
            "status": "in_progress",
            "level": 1,
            "expires_at": "2026-08-03 00:00:00",
        }
        player_info_module = MagicMock()
        player_info_module.player_info_cache = {
            "latest": {
                "building_training": {
                    "remainSecs": 7200,
                    "slotState": 1,
                    "trainee": {"charId": "char_test"},
                }
            }
        }

        with (
            patch.object(MasterySync, "_refresh_skland_data"),
            patch.object(mastery_sync, "has_train_group_plan", return_value=False),
            patch.object(mastery_sync, "get_in_progress_plan", return_value=plan),
            patch.object(mastery_sync, "set_plan_status") as set_status,
            patch.object(mastery_sync._os.path, "exists", return_value=False),
            patch.dict(
                "sys.modules",
                {"arknights_mower.solvers.player_info": player_info_module},
            ),
        ):
            sync = MasterySync(scheduler)
            sync.sync_and_schedule()
            first_refresh = scheduler.tasks[0]
            sync.sync_and_schedule()

        refresh_tasks = [
            task
            for task in scheduler.tasks
            if task.type == TaskTypes.REFRESH_TIME and task.meta_data == "train"
        ]
        self.assertEqual(refresh_tasks, [first_refresh])
        self.assertGreater(
            first_refresh.time,
            datetime.now() + timedelta(hours=1, minutes=59),
        )
        self.assertLess(
            first_refresh.time,
            datetime.now() + timedelta(hours=2, minutes=1),
        )
        saved_expiry = datetime.fromisoformat(set_status.call_args.kwargs["expires_at"])
        self.assertGreater(saved_expiry, datetime.now() + timedelta(hours=1, minutes=59))
        self.assertLess(saved_expiry, datetime.now() + timedelta(hours=2, minutes=1))

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_training_refresh_keeps_one_future_completion_trigger(self):
        solver = BaseSchedulerSolver()
        current = SchedulerTask(
            task_type=TaskTypes.REFRESH_TIME,
            meta_data="train",
        )
        solver.task = current
        solver.tasks = [current]
        solver.op_data = MagicMock()
        solver.op_data.skill_upgrade_supports = []
        player_info_module = MagicMock()
        player_info_module.player_info_cache = {
            "latest": {"building_training": {"trainer": {"charId": "char_optimal"}}}
        }
        completion_time = datetime.now() + timedelta(hours=6)

        with (
            patch.dict(
                "sys.modules",
                {"arknights_mower.solvers.player_info": player_info_module},
            ),
            patch(
                "arknights_mower.utils.mastery_recommendation.get_skill_data",
                return_value={
                    "characters": {"char_optimal": {"name": "逻各斯"}}
                },
            ),
        ):
            solver._calculate_swap_from_api(completion_time)
            future_refresh = solver.tasks[1]
            solver._calculate_swap_from_api(completion_time)

        self.assertEqual(len(solver.tasks), 2)
        self.assertIs(solver.tasks[1], future_refresh)
        self.assertEqual(future_refresh.type, TaskTypes.REFRESH_TIME)
        self.assertEqual(future_refresh.meta_data, "train")
        self.assertEqual(future_refresh.time, completion_time)

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_training_refresh_exception_keeps_completion_fallback(self):
        solver = BaseSchedulerSolver()
        current = SchedulerTask(
            task_type=TaskTypes.REFRESH_TIME,
            meta_data="train",
        )
        solver.task = current
        solver.tasks = [current]
        completion_time = datetime.now() + timedelta(hours=5)
        player_info_module = MagicMock()
        player_info_module.player_info_cache = {
            "latest": {"building_training": {"trainer": {}}}
        }

        with (
            patch.dict(
                "sys.modules",
                {"arknights_mower.solvers.player_info": player_info_module},
            ),
            patch(
                "arknights_mower.utils.mastery_db.get_in_progress_plan",
                return_value={
                    "char_id": "char_test",
                    "skill_index": 1,
                },
            ),
        ):
            solver._calculate_swap_from_api(completion_time)

        self.assertEqual(len(solver.tasks), 2)
        self.assertEqual(solver.tasks[1].type, TaskTypes.REFRESH_TIME)
        self.assertEqual(solver.tasks[1].meta_data, "train")
        self.assertEqual(solver.tasks[1].time, completion_time)

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_mastery_swap_and_refresh_follow_changed_eta(self):
        solver = BaseSchedulerSolver()
        current = SchedulerTask(
            task_type=TaskTypes.REFRESH_TIME,
            meta_data="train",
        )
        solver.task = current
        solver.tasks = [current]
        support = MagicMock()
        support.name = "Trainer"
        support.swap_name = "Swap"
        solver.op_data = MagicMock()
        solver.op_data.skill_upgrade_supports = [support]
        solver.op_data.calculate_switch_time.side_effect = [2, 4]
        player_info_module = MagicMock()
        player_info_module.player_info_cache = {
            "latest": {
                "building_training": {
                    "trainer": {"charId": "char_trainer"},
                }
            }
        }
        first_completion = datetime.now() + timedelta(hours=8)
        second_completion = first_completion + timedelta(hours=1)

        with (
            patch.dict(
                "sys.modules",
                {"arknights_mower.solvers.player_info": player_info_module},
            ),
            patch(
                "arknights_mower.utils.mastery_db.get_in_progress_plan",
                return_value={
                    "char_id": "char_test",
                    "skill_index": 1,
                },
            ),
            patch(
                "arknights_mower.utils.mastery_recommendation.get_skill_data",
                return_value={
                    "characters": {"char_trainer": {"name": "Trainer"}}
                },
            ),
        ):
            solver._calculate_swap_from_api(first_completion)
            swap_task = next(
                task for task in solver.tasks if task.meta_data == "_mastery"
            )
            first_swap_time = swap_task.time
            solver._calculate_swap_from_api(second_completion)

        swap_tasks = [
            task for task in solver.tasks if task.meta_data == "_mastery"
        ]
        refresh_tasks = [
            task
            for task in solver.tasks
            if task is not current
            and task.type == TaskTypes.REFRESH_TIME
            and task.meta_data == "train"
        ]
        self.assertEqual(swap_tasks, [swap_task])
        self.assertGreater(swap_task.time, first_swap_time)
        self.assertEqual(
            getattr(swap_task, "mastery_plan_key"),
            "char_test_1",
        )
        self.assertEqual(len(refresh_tasks), 1)
        self.assertEqual(
            refresh_tasks[0].time,
            swap_task.time + timedelta(seconds=1),
        )

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_training_completion_brings_existing_next_level_task_due(self):
        solver = BaseSchedulerSolver()
        solver.task = SchedulerTask(
            task_type=TaskTypes.REFRESH_TIME,
            meta_data="train",
        )
        first = SchedulerTask(
            time=datetime.now() + timedelta(hours=3),
            task_type=TaskTypes.SKILL_UPGRADE,
            meta_data="old",
        )
        first.plan_key = "char_test_2"
        duplicate = SchedulerTask(
            time=datetime.now() + timedelta(hours=4),
            task_type=TaskTypes.SKILL_UPGRADE,
            meta_data="duplicate",
        )
        duplicate.plan_key = "char_test_2"
        solver.tasks = [solver.task, first, duplicate]
        player_info_module = MagicMock()
        player_info_module.player_info_cache = {
            "latest": {
                "building_training": {
                    "trainee": {
                        "charId": "char_test",
                        "targetSkill": -1,
                    }
                }
            }
        }
        before = datetime.now()

        with (
            patch.dict(
                "sys.modules",
                {"arknights_mower.solvers.player_info": player_info_module},
            ),
            patch(
                "arknights_mower.utils.mastery_db.get_in_progress_plan",
                return_value={
                    "char_id": "char_test",
                    "skill_index": 2,
                    "level": 1,
                },
            ),
            patch(
                "arknights_mower.utils.mastery_db.insert_plan"
            ) as insert_plan,
            patch(
                "arknights_mower.utils.mastery_recommendation.get_skill_data",
                return_value={
                    "characters": {"char_test": {"name": "Test"}}
                },
            ),
        ):
            solver._handle_training_complete()

        next_tasks = [
            task
            for task in solver.tasks
            if task.type == TaskTypes.SKILL_UPGRADE
            and getattr(task, "plan_key", "") == "char_test_2"
        ]
        self.assertEqual(next_tasks, [first])
        self.assertGreaterEqual(first.time, before)
        self.assertLessEqual(first.time, datetime.now())
        self.assertEqual(first.meta_data, "Test 技能3")
        self.assertEqual(insert_plan.call_count, 2)

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_immediate_trade_drone_checks_limit_before_first_acceleration(self):
        solver = BaseSchedulerSolver()
        solver.tasks = []
        solver.task = SchedulerTask()
        solver.op_data = MagicMock()
        solver.op_data.run_order_rooms = {"room_1_1": []}
        solver.drone_room = None
        solver.recog = MagicMock()
        solver.digit_reader = MagicMock()
        solver.digit_reader.get_drone.return_value = 113
        solver.waiting_scene = set()
        solver.enter_room = MagicMock()
        solver.tap = MagicMock()
        solver.tap_element = MagicMock()
        solver.accept_order = MagicMock()
        solver.scene_graph_navigation = MagicMock()
        bill_accelerate = object()
        solver.find = MagicMock(
            side_effect=lambda name, *args, **kwargs: (
                bill_accelerate if name == "bill_accelerate" else None
            )
        )

        with patch.object(base_schedule.config.conf, "drone_count_limit", 120):
            solver.drone("room_1_1", not_customize=True)

        solver.digit_reader.get_drone.assert_called_once()
        solver.tap_element.assert_not_called()
        solver.accept_order.assert_not_called()

class TestMergeRunOrder(unittest.TestCase):
    def _make_run_order(self, time, room):
        return SchedulerTask(
            time=time, task_type=TaskTypes.RUN_ORDER, meta_data=room
        )

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_merge_run_order_tasks_pulls_next_task_closer(self):
        # 间隔20分钟的相邻跑单任务被拉近至配置的最终目标间隔处
        solver = BaseSchedulerSolver()
        # find_run_order_merge_pair 只处理未来任务，需以当前时间为基准
        now = datetime.now()
        prev = self._make_run_order(now + timedelta(minutes=10), "room_1_1")
        nxt = self._make_run_order(now + timedelta(minutes=30), "room_1_2")
        solver.tasks = [nxt, prev]
        drone_calls = []

        def fake_drone(room, adjust_time=False, merge_target=None):
            drone_calls.append(room)
            target_time, threshold_floor = merge_target
            task = find_next_task(
                solver.tasks, task_type=TaskTypes.RUN_ORDER, meta_data=room
            )
            task.time = target_time

        with (
            patch.object(base_schedule.config.conf, "run_order_delay", 3),
            patch.object(
                base_schedule.config.conf.run_order_grandet_mode, "merge_interval", 8
            ),
            patch.object(BaseSchedulerSolver, "drone", side_effect=fake_drone),
        ):
            solver.merge_run_order_tasks()

        # 合并后目标间隔为 8 分钟
        self.assertEqual(drone_calls, ["room_1_2"])
        self.assertEqual(nxt.time, prev.time + timedelta(minutes=8))
        # 任务列表被重新排序
        self.assertEqual(solver.tasks, [prev, nxt])

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_merge_run_order_tasks_pulls_next_task_to_non_run_anchor(self):
        solver = BaseSchedulerSolver()
        now = datetime.now()
        prev = self._make_run_order(now + timedelta(minutes=10), "room_1_1")
        shift = SchedulerTask(
            time=now + timedelta(minutes=20),
            task_type=TaskTypes.SHIFT_ON,
            meta_data="shift_on",
        )
        nxt = self._make_run_order(now + timedelta(minutes=30), "room_1_2")
        solver.tasks = [nxt, prev, shift]

        def fake_drone(room, adjust_time=False, merge_target=None):
            target_time, _ = merge_target
            task = find_next_task(
                solver.tasks, task_type=TaskTypes.RUN_ORDER, meta_data=room
            )
            task.time = target_time

        with (
            patch.object(base_schedule.config.conf, "run_order_delay", 3),
            patch.object(
                base_schedule.config.conf.run_order_grandet_mode, "merge_interval", 8
            ),
            patch.object(
                BaseSchedulerSolver, "drone", side_effect=fake_drone
            ) as mock_drone,
        ):
            solver.merge_run_order_tasks()

        mock_drone.assert_called_once()
        self.assertEqual(nxt.time, shift.time + timedelta(minutes=8))
        self.assertEqual(solver.tasks, [prev, shift, nxt])

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_merge_run_order_tasks_stops_without_progress(self):
        # 加速无进展（如无人机不足）时应停止，不会死循环
        solver = BaseSchedulerSolver()
        now = datetime.now()
        prev = self._make_run_order(now + timedelta(minutes=10), "room_1_1")
        nxt = self._make_run_order(now + timedelta(minutes=30), "room_1_2")
        solver.tasks = [prev, nxt]

        with (
            patch.object(base_schedule.config.conf, "run_order_delay", 3),
            patch.object(
                base_schedule.config.conf.run_order_grandet_mode, "merge_interval", 8
            ),
            patch.object(BaseSchedulerSolver, "drone") as mock_drone,
        ):
            solver.merge_run_order_tasks()

        self.assertEqual(mock_drone.call_count, 1)
        self.assertEqual(nxt.time, now + timedelta(minutes=30))

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_merge_order_time_stops_above_threshold_floor(self):
        # 无人机逐步加速订单，最终跑单时间不低于安全下限
        solver = BaseSchedulerSolver()
        now = datetime(2026, 7, 6, 10, 0)
        prev_time = now + timedelta(minutes=10)
        threshold_floor = prev_time + timedelta(minutes=3)
        target_time = prev_time + timedelta(minutes=8)
        task = self._make_run_order(now + timedelta(minutes=30), "room_1_2")
        solver.tasks = [task]
        solver.recog = MagicMock(w=1920, h=1080, gray=None)
        solver.digit_reader = MagicMock()
        solver.digit_reader.get_drone.return_value = 200
        solver.waiting_scene = []
        solver.scene = MagicMock(return_value=None)
        solver.find = MagicMock(return_value=(0, 0))

        # 模拟每台无人机减少 3 分钟订单时间
        state = {"completion": now + timedelta(minutes=33), "presses": 0}
        plus_coord = (1920 * 1320 // 1920, 1080 * 502 // 1080)

        def fake_tap(pos, interval=None, **kwargs):
            if pos == plus_coord:
                state["presses"] += 1
                state["completion"] -= timedelta(minutes=3)

        solver.tap = fake_tap
        solver.double_read_time = lambda *args, **kwargs: state["completion"]

        with (
            patch.object(base_schedule.config.conf, "run_order_delay", 3),
            patch.object(base_schedule.config.conf, "drone_count_limit", 100),
        ):
            solver.merge_order_time((0, 0), "room_1_2", target_time, threshold_floor)

        self.assertGreaterEqual(task.time, threshold_floor)
        self.assertLessEqual(task.time, target_time)
        self.assertGreater(state["presses"], 0)

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_merge_order_time_respects_drone_count_limit(self):
        # 无人机数量不高于使用阈值时不加速
        solver = BaseSchedulerSolver()
        now = datetime(2026, 7, 6, 10, 0)
        threshold_floor = now + timedelta(minutes=15)
        target_time = threshold_floor + timedelta(minutes=2)
        task = self._make_run_order(now + timedelta(minutes=30), "room_1_2")
        solver.tasks = [task]
        solver.recog = MagicMock(w=1920, h=1080, gray=None)
        solver.digit_reader = MagicMock()
        solver.digit_reader.get_drone.return_value = 100
        solver.tap = MagicMock()

        with patch.object(base_schedule.config.conf, "drone_count_limit", 100):
            solver.merge_order_time((0, 0), "room_1_2", target_time, threshold_floor)

        solver.tap.assert_not_called()
        self.assertEqual(task.time, now + timedelta(minutes=30))


if __name__ == "__main__":
    unittest.main()
