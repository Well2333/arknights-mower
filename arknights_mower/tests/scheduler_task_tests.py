import pickle
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from arknights_mower.utils.operators import (
    Dormitory,
    Operator,
    Operators,
    reconcile_saved_dormitories,
)
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    calculate_shift_on_mood,
    check_dorm_ordering,
    collect_shift_on_readiness,
    defer_tasks_before_next_run_order,
    delay_shift_on_tasks_until_ready,
    estimate_mood_ready_at,
    find_immediate_run_order,
    find_next_task,
    find_run_order_merge_pair,
    find_task_batch_end,
    plan_metadata,
    parse_scheduler_task_time,
    sanitize_self_correction_plan,
    shift_on_readiness_retry_names,
    scheduling,
    shift_on_not_before,
    try_add_release_dorm,
    try_reorder,
)

with patch.dict("sys.modules", {"save_action_to_sqlite_decorator": MagicMock()}):
    pass


class TestScheduling(unittest.TestCase):
    def test_parse_scheduler_task_time_respects_existing_offset(self):
        china = timezone(timedelta(hours=8))

        local_value = parse_scheduler_task_time(
            "2026-08-02T22:30:00.000000+08:00", china
        )
        utc_value = parse_scheduler_task_time(
            "2026-08-02T14:30:00.000000+00:00", china
        )

        expected = datetime(2026, 8, 2, 22, 30)
        self.assertEqual(local_value, expected)
        self.assertEqual(utc_value, expected)

    def test_restore_dorms_keeps_current_plan_slots_and_recovers_new_occupants(self):
        old_time = datetime(2026, 8, 3, 7, 30)
        planned = [
            Dormitory(("dormitory_1", 3)),
            Dormitory(("dormitory_1", 4)),
            Dormitory(("dormitory_4", 2)),
        ]
        saved = [
            Dormitory(("dormitory_1", 4), "灰烬", old_time),
            Dormitory(("dormitory_2", 2), "已移除床位", old_time),
        ]
        operators = {
            "凯尔希": Operator(
                "凯尔希",
                "room_2_2",
                current_room="dormitory_1",
                current_index=3,
            ),
            "灰烬": Operator(
                "灰烬",
                "room_2_2",
                current_room="dormitory_1",
                current_index=4,
            ),
            "阿罗玛": Operator(
                "阿罗玛",
                "room_1_3",
                current_room="dormitory_4",
                current_index=2,
            ),
        }

        result = reconcile_saved_dormitories(planned, saved, operators)

        self.assertEqual(len(result), 3)
        self.assertEqual([dorm.name for dorm in result], ["凯尔希", "灰烬", "阿罗玛"])
        self.assertIsNone(result[0].time)
        self.assertEqual(result[1].time, old_time)
        self.assertIsNone(result[2].time)

    def test_adjust_two_orders(self):
        # 测试两个跑单任务被拉开
        task1 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 1"},
            task_type=TaskTypes.RUN_ORDER,
        )
        task2 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:01", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 2"},
        )
        task3 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:02", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 3"},
        )
        task4 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:02", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 4"},
            task_type=TaskTypes.RUN_ORDER,
        )
        task5 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:30", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 5"},
        )
        tasks = [task1, task2, task3, task4, task5]
        res = scheduling(
            tasks, time_now=datetime.strptime("2023-09-19 09:01", "%Y-%m-%d %H:%M")
        )
        # 返还的是应该拉开跑单的任务
        self.assertNotEqual(res, None)

    def test_adjust_two_orders_fia(self):
        # 测试菲亚换班时间预设3分钟有效
        task1 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 1"},
        )
        task2 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:01", "%Y-%m-%d %H:%M"),
            task_plan={},
            task_type=TaskTypes.FIAMMETTA,
        )
        task4 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:03", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 4"},
            task_type=TaskTypes.RUN_ORDER,
        )
        task5 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:30", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 5"},
        )
        tasks = [task1, task2, task4, task5]
        scheduling(
            tasks, time_now=datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M")
        )
        # 跑单任务被提前
        self.assertEqual(tasks[0].type, TaskTypes.RUN_ORDER)

    def test_adjust_time(self):
        # 测试跑单任务被挤兑
        task1 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 1"},
            task_type=TaskTypes.RUN_ORDER,
        )
        task2 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:01", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 2"},
        )
        task3 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:02", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 3"},
        )
        task4 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:03", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 4"},
            task_type=TaskTypes.RUN_ORDER,
        )
        task5 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:30", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 5"},
        )
        tasks = [task1, task2, task3, task4, task5]
        res = scheduling(
            tasks, time_now=datetime.strptime("2023-09-19 10:01", "%Y-%m-%d %H:%M")
        )
        # 其他任务会被移送至跑单任务以后
        self.assertEqual(tasks[2].plan["task"], "Task 4")
        self.assertEqual(res, None)

    def _make_run_order(self, time_str, room, adjusted=False, run_order=True):
        return SchedulerTask(
            time=datetime.fromisoformat(time_str),
            task_type=TaskTypes.RUN_ORDER if run_order else TaskTypes.SHIFT_ON,
            meta_data=room,
            adjusted=adjusted,
        )

    def test_find_immediate_run_order_selects_nearest_and_checks_interval(self):
        time_now = datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M")
        nearest = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:10", "%Y-%m-%d %H:%M"),
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room_1_1",
        )
        later = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:20", "%Y-%m-%d %H:%M"),
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room_1_2",
        )

        target = find_immediate_run_order([later, nearest], time_now=time_now)

        self.assertIs(target, nearest)
        self.assertIs(
            find_immediate_run_order(
                [later, nearest], time_now=time_now, exclude_task=nearest
            ),
            later,
        )

        later.time = datetime.strptime("2023-09-19 10:02", "%Y-%m-%d %H:%M")
        nearest.time = datetime.strptime("2023-09-19 10:02:30", "%Y-%m-%d %H:%M:%S")
        target = find_immediate_run_order([nearest, later], time_now=time_now)
        self.assertIs(target, later)

    def test_find_task_batch_end_uses_strict_three_minute_gap(self):
        time_now = datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M")
        first = SchedulerTask(time=time_now, task_type=TaskTypes.SHIFT_ON)
        second = SchedulerTask(
            time=time_now + timedelta(minutes=2), task_type=TaskTypes.WORKSHOP
        )
        third = SchedulerTask(
            time=time_now + timedelta(minutes=4), task_type=TaskTypes.RUN_ORDER
        )
        fourth = SchedulerTask(
            time=time_now + timedelta(minutes=7), task_type=TaskTypes.SHIFT_ON
        )

        self.assertEqual(
            find_task_batch_end([first, second, third, fourth], second), third.time
        )

    def test_defer_tasks_before_next_run_order_preserves_order(self):
        time_now = datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M")
        overdue = SchedulerTask(
            time=time_now - timedelta(minutes=1),
            task_type=TaskTypes.SHIFT_ON,
            meta_data="overdue",
        )
        current = SchedulerTask(
            time=time_now,
            task_type=TaskTypes.WORKSHOP,
            meta_data="current",
        )
        before = SchedulerTask(
            time=time_now + timedelta(minutes=5),
            task_type=TaskTypes.SHIFT_OFF,
            meta_data="before",
        )
        target = SchedulerTask(
            time=time_now + timedelta(minutes=10),
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room_1_1",
        )
        same_time = SchedulerTask(
            time=target.time,
            task_type=TaskTypes.RECRUIT,
            meta_data="same_time",
        )
        later = SchedulerTask(
            time=time_now + timedelta(minutes=20),
            task_type=TaskTypes.SHIFT_ON,
            meta_data="later",
        )
        next_run_order = SchedulerTask(
            time=time_now + timedelta(minutes=30),
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room_1_2",
        )
        tasks = [later, same_time, target, current, next_run_order, before, overdue]

        selected, deferred = defer_tasks_before_next_run_order(
            tasks,
            time_now=time_now,
            exclude_task=current,
        )

        self.assertIs(selected, target)
        self.assertEqual(deferred, [overdue, before, same_time])
        self.assertEqual(current.time, time_now)
        self.assertEqual(overdue.time, target.time + timedelta(seconds=1))
        self.assertEqual(before.time, target.time + timedelta(seconds=2))
        self.assertEqual(same_time.time, target.time + timedelta(seconds=3))
        self.assertEqual(later.time, time_now + timedelta(minutes=20))
        self.assertEqual(next_run_order.time, time_now + timedelta(minutes=30))
        self.assertEqual(tasks[1:5], [target, overdue, before, same_time])

    def test_defer_tasks_before_next_run_order_handles_empty_candidates(self):
        time_now = datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M")
        later = SchedulerTask(
            time=time_now + timedelta(minutes=5), task_type=TaskTypes.SHIFT_ON
        )

        target, deferred = defer_tasks_before_next_run_order(
            [later], time_now=time_now
        )

        self.assertIsNone(target)
        self.assertEqual(deferred, [])

    def test_scheduler_task_immediate_flag_defaults_to_false(self):
        normal = SchedulerTask(task_type=TaskTypes.RUN_ORDER)
        immediate = SchedulerTask(task_type=TaskTypes.RUN_ORDER, immediate=True)

        self.assertFalse(normal.immediate)
        self.assertTrue(immediate.immediate)

    def test_find_run_order_merge_pair(self):
        # 间隔20分钟的两个跑单任务应被识别为可合并
        time_now = datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M")
        tasks = [
            self._make_run_order("2023-09-19 10:10", "room_1_1"),
            self._make_run_order("2023-09-19 10:30", "room_1_2"),
        ]
        pair = find_run_order_merge_pair(
            tasks, run_order_delay=3, merge_interval=8, time_now=time_now
        )
        self.assertIsNotNone(pair)
        self.assertEqual(pair[0].meta_data, "room_1_1")
        self.assertEqual(pair[1].meta_data, "room_1_2")
        self.assertEqual(pair[2], tasks[0].time + timedelta(minutes=8))
        self.assertEqual(pair[3], tasks[0].time + timedelta(minutes=3))
        # 输入值代表合并后的最终间隔，不再把安全间隔和额外余量叠加到输入值上
        tasks[1].time = tasks[0].time + timedelta(minutes=5)
        res = scheduling(tasks, run_order_delay=3, time_now=time_now)
        self.assertIsNone(res)

    def test_find_run_order_merge_pair_skip(self):
        time_now = datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M")
        # 已经足够接近，不合并
        tasks = [
            self._make_run_order("2023-09-19 10:10", "room_1_1"),
            self._make_run_order("2023-09-19 10:17", "room_1_2"),
        ]
        self.assertIsNone(
            find_run_order_merge_pair(
                tasks, run_order_delay=3, merge_interval=8, time_now=time_now
            )
        )
        # 提前量超过固定保护上限，不合并
        tasks = [
            self._make_run_order("2023-09-19 10:10", "room_1_1"),
            self._make_run_order("2023-09-19 10:50", "room_1_2"),
        ]
        self.assertIsNone(
            find_run_order_merge_pair(
                tasks, run_order_delay=3, merge_interval=8, time_now=time_now
            )
        )
        # 维护期被调整过的任务不合并
        tasks = [
            self._make_run_order("2023-09-19 10:10", "room_1_1"),
            self._make_run_order("2023-09-19 10:30", "room_1_2", adjusted=True),
        ]
        self.assertIsNone(
            find_run_order_merge_pair(
                tasks, run_order_delay=3, merge_interval=8, time_now=time_now
            )
        )
        # 已经过去的任务不参与合并；没有未来锚点时不移动跑单
        tasks = [
            self._make_run_order("2023-09-19 09:10", "room_1_1"),
            self._make_run_order("2023-09-19 10:30", "room_1_3"),
        ]
        self.assertIsNone(
            find_run_order_merge_pair(
                tasks, run_order_delay=3, merge_interval=8, time_now=time_now
            )
        )

    def test_find_run_order_merge_pair_uses_nearest_non_run_anchor(self):
        # 跑单会优先贴近最近的普通任务，而不是只贴近上一个跑单
        time_now = datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M")
        tasks = [
            self._make_run_order("2023-09-19 10:10", "room_1_1"),
            self._make_run_order("2023-09-19 10:20", "shift_on", run_order=False),
            self._make_run_order("2023-09-19 10:30", "room_1_2"),
        ]

        anchor, run_order, target_time, threshold_floor = find_run_order_merge_pair(
            tasks, run_order_delay=3, merge_interval=8, time_now=time_now
        )

        self.assertEqual(anchor.meta_data, "shift_on")
        self.assertEqual(run_order.meta_data, "room_1_2")
        self.assertEqual(
            threshold_floor,
            datetime.strptime("2023-09-19 10:20", "%Y-%m-%d %H:%M"),
        )
        self.assertEqual(
            target_time, datetime.strptime("2023-09-19 10:28", "%Y-%m-%d %H:%M")
        )

    def test_find_run_order_merge_pair_uses_input_as_final_interval(self):
        time_now = datetime.strptime("2023-07-10 17:00", "%Y-%m-%d %H:%M")
        tasks = [
            self._make_run_order("2023-07-10 17:21:08", "room_2_1"),
            self._make_run_order("2023-07-10 17:29:23", "room_1_1"),
        ]

        pair = find_run_order_merge_pair(
            tasks, run_order_delay=3, merge_interval=8, time_now=time_now
        )

        self.assertIsNotNone(pair)
        self.assertEqual(
            pair[2], datetime.strptime("2023-07-10 17:29:08", "%Y-%m-%d %H:%M:%S")
        )

    def test_find_run_order_merge_pair_clamps_minimum_interval(self):
        time_now = datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M")
        tasks = [
            self._make_run_order("2023-09-19 10:10", "room_1_1"),
            self._make_run_order("2023-09-19 10:20", "room_1_2"),
        ]

        pair = find_run_order_merge_pair(
            tasks, run_order_delay=3, merge_interval=3, time_now=time_now
        )

        self.assertIsNotNone(pair)
        self.assertEqual(pair[2], tasks[0].time + timedelta(minutes=5))

    def test_immediate_flag_survives_restart_state_pickle(self):
        task = SchedulerTask(
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room_1_1",
            immediate=True,
        )

        restored = pickle.loads(pickle.dumps(task))

        self.assertTrue(restored.immediate)
        self.assertEqual(restored.type, TaskTypes.RUN_ORDER)

    def test_find_next(self):
        # 测试 方程有效
        task1 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 1"},
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room",
        )
        task4 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:03", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 4"},
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room",
        )
        task5 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:30", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 5"},
        )
        tasks = [task1, task4, task5]
        now = datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M")
        res1 = find_next_task(
            tasks,
            now + timedelta(minutes=5),
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room",
            compare_type=">",
        )
        res2 = find_next_task(
            tasks,
            now + timedelta(minutes=-60),
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room",
            compare_type=">",
        )
        self.assertEqual(res1, None)
        self.assertNotEqual(res2, None)

    def test_check_dorm_ordering_add_plan_1(self):
        # 测试 方程有效
        task1 = SchedulerTask(
            time=datetime.now(),
            task_plan={
                "dormitory_1": ["Current", "Current", "夕", "Current", "Current"],
                "central": ["麒麟R夜刀", "Current", "Current", "Current", "Current"],
            },
            task_type=TaskTypes.SHIFT_OFF,
            meta_data="",
        )
        tasks = [task1]
        op_data = self.init_opdata()
        check_dorm_ordering(tasks, op_data)
        # 生成额外宿舍任务
        self.assertEqual(2, len(tasks))
        # 验证第一个宿舍任务包含换班+宿舍任务
        self.assertEqual(2, len(tasks[0].plan))
        # 老plan含有见行者
        self.assertEqual("见行者", tasks[1].plan["dormitory_1"][3])
        # 假设换班任务执行完毕
        del tasks[0]
        # 重复执行不会生成新的
        check_dorm_ordering(tasks, op_data)
        self.assertEqual(1, len(tasks))
        # 验证第二个任务仅仅包宿舍任务
        self.assertEqual(1, len(tasks[0].plan))

    def test_check_dorm_ordering_add_plan_2(self):
        # 测试 方程有效
        task1 = SchedulerTask(
            time=datetime.now(),
            task_plan={
                "dormitory_1": ["Current", "Current", "夕", "Current", "Current"],
                "central": ["麒麟R夜刀", "Current", "Current", "Current", "Current"],
            },
            task_type=TaskTypes.SHIFT_OFF,
            meta_data="",
        )
        tasks = [task1]
        op_data = self.init_opdata()
        # 预设干员位置
        op_data.operators["见行者"].current_index = -1
        op_data.operators["见行者"].current_room = "meeting"
        op_data.operators["麒麟R夜刀"].current_index = 3
        op_data.operators["麒麟R夜刀"].current_room = "dormitory_1"
        check_dorm_ordering(tasks, op_data)
        # 生成额外宿舍任务
        self.assertEqual(2, len(tasks))
        # 验证第一个宿舍任务包含换班+宿舍任务
        self.assertEqual(2, len(tasks[0].plan))
        # 老plan不变
        self.assertEqual("Free", tasks[1].plan["dormitory_1"][3])
        # 假设换班任务执行完毕
        del tasks[0]
        # 重复执行不会生成新的
        check_dorm_ordering(tasks, op_data)
        self.assertEqual(1, len(tasks))
        # 验证第二个任务仅仅包宿舍任务
        self.assertEqual(1, len(tasks[0].plan))

    def test_check_dorm_ordering_add_plan_3(self):
        # 测试 宿舍4号位置已经吃到VIP的情况，安排新的高效干员去3号位置刷新VIP
        task1 = SchedulerTask(
            time=datetime.now(),
            task_plan={
                "dormitory_1": ["Current", "Current", "Current", "夕", "Current"],
                "central": ["麒麟R夜刀", "Current", "Current", "Current", "Current"],
            },
            task_type=TaskTypes.SHIFT_OFF,
            meta_data="",
        )
        tasks = [task1]
        op_data = self.init_opdata()
        # 预设干员位置
        op_data.operators["红"].current_index = -1
        op_data.operators["红"].current_room = "meeting"
        op_data.operators["夕"].resting_priority = "low"
        op_data.operators["焰尾"].current_index = 2
        op_data.operators["焰尾"].current_room = "dormitory_1"
        check_dorm_ordering(tasks, op_data)

        # 如果非VIP位置被占用，则刷新
        self.assertEqual(1, len(tasks))
        # 验证第任务包含换班+宿舍任务
        self.assertEqual(2, len(tasks[0].plan))
        # 假设换班任务执行完毕
        del tasks[0]
        # 重复执行不会生成新的
        check_dorm_ordering(tasks, op_data)
        self.assertEqual(0, len(tasks))

    def test_check_dorm_ordering_add_plan_4(self):
        # 测试 方程有效
        task1 = SchedulerTask(
            time=datetime.now(),
            task_plan={
                "dormitory_1": ["Current", "Current", "夕", "Current", "Current"],
                "central": ["麒麟R夜刀", "Current", "Current", "Current", "Current"],
            },
            task_type=TaskTypes.SHIFT_OFF,
            meta_data="",
        )
        tasks = [task1]
        op_data = self.init_opdata()
        op_data.operators["玛恩纳"].current_room = ""
        op_data.operators["玛恩纳"].current_index = -1
        check_dorm_ordering(tasks, op_data)
        # 生成额外宿舍任务
        self.assertEqual(2, len(tasks))
        # 验证第一个宿舍任务包含换班+宿舍任务
        self.assertEqual(2, len(tasks[0].plan))
        # 老plan含有见行者
        self.assertEqual("见行者", tasks[1].plan["dormitory_1"][3])
        # 假设换班任务执行完毕
        del tasks[0]
        # 重复执行不会生成新的
        check_dorm_ordering(tasks, op_data)
        self.assertEqual(1, len(tasks))
        # 验证第二个任务仅仅包宿舍任务
        self.assertEqual(1, len(tasks[0].plan))

    def test_check_dorm_ordering_not_plan(self):
        # 测试 如果当前已经有前置位VIP干员在吃单回，则不会新增任务
        task1 = SchedulerTask(
            time=datetime.now(),
            task_plan={
                "dormitory_1": ["Current", "Current", "Current", "夕", "令"],
                "central": ["麒麟R夜刀", "Current", "Current", "Current", "火龙S黑角"],
            },
            task_type=TaskTypes.SHIFT_OFF,
            meta_data="",
        )
        tasks = [task1]
        op_data = self.init_opdata()
        # 预设干员位置
        op_data.operators["红"].current_index = -1
        op_data.operators["夕"].resting_priority = "low"
        op_data.operators["红"].current_room = "meeting"
        op_data.operators["焰尾"].current_index = 2
        op_data.operators["焰尾"].current_room = "dormitory_1"
        check_dorm_ordering(tasks, op_data)

        # 如果VIP位已经被占用，则不会生成新任务
        self.assertEqual(1, len(tasks))
        # 验证第任务包含换班+宿舍任务
        self.assertEqual(2, len(tasks[0].plan))
        # 重复执行不会生成新的
        check_dorm_ordering(tasks, op_data)
        self.assertEqual(1, len(tasks))
        # 验证第任务包宿舍+换班任务
        self.assertEqual(2, len(tasks[0].plan))

    def test_check_dorm_ordering_not_plan2(self):
        # 测试 如果当前已经有前置位VIP干员在吃单回，则不会新增任务
        task1 = SchedulerTask(
            time=datetime.now(),
            task_plan={
                "dormitory_1": ["Current", "Current", "Current", "夕", "Current"],
                "central": ["麒麟R夜刀", "Current", "Current", "Current", "Current"],
            },
            task_type=TaskTypes.SHIFT_OFF,
            meta_data="",
        )
        tasks = [task1]
        op_data = self.init_opdata()
        # 预设干员位置
        op_data.operators["红"].current_index = 2
        op_data.operators["红"].current_room = "dormitory_1"
        op_data.operators["夕"].resting_priority = "low"
        op_data.operators["红"].current_room = "meeting"
        check_dorm_ordering(tasks, op_data)

        # 如果VIP位已经被占用，则不会生成新任务
        self.assertEqual(1, len(tasks))
        # 验证第任务包含换班+宿舍任务
        self.assertEqual(2, len(tasks[0].plan))
        # 重复执行不会生成新的
        check_dorm_ordering(tasks, op_data)
        self.assertEqual(1, len(tasks))
        # 验证第任务包宿舍+换班任务
        self.assertEqual(2, len(tasks[0].plan))

    def test_adjust_three_orders(self):
        # 测试342跑单任务被拉开
        task1 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M"),
            task_plan={"task1": "Task 1"},
            task_type=TaskTypes.RUN_ORDER,
            meta_data="task1",
        )
        task2 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:01", "%Y-%m-%d %H:%M"),
            task_plan={"task2": "Task 2"},
            task_type=TaskTypes.RUN_ORDER,
            meta_data="task2",
        )
        task3 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:02", "%Y-%m-%d %H:%M"),
            task_plan={"task3": "Task 3"},
            task_type=TaskTypes.RUN_ORDER,
            meta_data="task3",
        )
        tasks = [task1, task2, task3]
        res = scheduling(
            tasks, time_now=datetime.strptime("2023-09-19 09:01", "%Y-%m-%d %H:%M")
        )

        while res is not None and res[0].meta_data == "task1":
            task_time = res[0].time - timedelta(minutes=(2))
            task = find_next_task(
                tasks, task_type=TaskTypes.RUN_ORDER, meta_data="task1"
            )
            if task is not None:
                task.time = task_time
                res = scheduling(
                    tasks,
                    time_now=datetime.strptime("2023-09-19 09:03", "%Y-%m-%d %H:%M"),
                )
            else:
                break
        # 返还的是应该拉开跑单的任务
        self.assertNotEqual(res, None)

    def test_reorder_1(self):
        # 高优先级被拉前面
        op_data = self.init_opdata()
        op_data.dorm[0].name = "麒麟R夜刀"
        op_data.dorm[1].name = "凯尔希"
        op_data.operators["凯尔希"].current_room = "dormitory_2"
        op_data.operators["凯尔希"].current_index = 2
        op_data.dorm[2].name = "夕"
        plan = try_reorder(op_data, {})
        self.assertEqual(plan["dormitory_1"][2], "夕")
        tasks = [SchedulerTask(task_plan=plan, task_type=TaskTypes.SHIFT_OFF)]
        check_dorm_ordering(tasks, op_data)
        self.assertEqual(len(tasks), 2)

    def test_reorder_2(self):
        # 非高优高效不会被移动
        op_data = self.init_opdata()
        op_data.dorm[0].name = "麒麟R夜刀"
        op_data.dorm[1].name = "凯尔希"
        op_data.dorm[2].name = "夕"
        op_data.dorm[3].name = "见行者"
        op_data.dorm[4].name = "森蚺"

        # op_data.config.ope_resting_priority=["森蚺","夕"]
        plan = try_reorder(op_data, {})
        self.assertEqual(len(plan), 3)
        self.assertEqual(plan["dormitory_1"][2], "夕")
        self.assertEqual(plan["dormitory_1"][4], "凯尔希")
        tasks = [SchedulerTask(task_plan=plan, task_type=TaskTypes.SHIFT_OFF)]
        check_dorm_ordering(tasks, op_data)
        self.assertEqual(len(tasks), 2)

    def test_reorder_3(self):
        # 如果高优都占了，则不动
        op_data = self.init_opdata()
        op_data.dorm[0].name = "夕"
        op_data.dorm[1].name = "焰尾"
        op_data.dorm[2].name = "森蚺"
        op_data.dorm[3].name = "玛恩纳"
        op_data.operators["见行者"].current_room = "dormitory_2"
        op_data.operators["见行者"].current_index = 2
        op_data.dorm[4].name = "见行者"
        try_reorder(op_data, {})
        plan = try_reorder(op_data, {})
        self.assertEqual(plan["dormitory_1"][2], "夕")
        self.assertEqual(plan["dormitory_1"][3], "见行者")
        tasks = [SchedulerTask(task_plan=plan, task_type=TaskTypes.SHIFT_OFF)]
        check_dorm_ordering(tasks, op_data)
        self.assertEqual(len(tasks), 2)

    def init_opdata(self):
        agent_base_config = PlanConfig(
            "稀音,黑键,伊内丝,承曦格雷伊", "稀音,柏喙,伊内丝", "见行者"
        )
        plan_config = {
            "central": [
                Room("夕", "", ["麒麟R夜刀"]),
                Room("焰尾", "", ["凯尔希"]),
                Room("森蚺", "", ["凯尔希"]),
                Room("令", "", ["火龙S黑角"]),
                Room("薇薇安娜", "", ["玛恩纳"]),
            ],
            "meeting": [
                Room("伊内丝", "", ["陈", "红"]),
                Room("见行者", "", ["陈", "红"]),
            ],
            "dormitory_1": [
                Room("塑心", "", []),
                Room("冰酿", "", []),
                Room("Free", "", []),
                Room("Free", "", []),
                Room("Free", "", []),
            ],
            "dormitory_2": [
                Room("琴柳", "", []),
                Room("阿米娅", "", []),
                Room("Free", "", []),
                Room("Free", "", []),
                Room("Free", "", []),
            ],
            "dormitory_3": [
                Room("迷迭香", "", []),
                Room("杜林", "", []),
                Room("月见夜", "", []),
                Room("Free", "", []),
                Room("Free", "", []),
            ],
        }
        plan = {
            "default_plan": Plan(plan_config, agent_base_config),
            "backup_plans": [],
        }
        op_data = Operators(plan)
        op_data.init_and_validate()
        # 预设干员位置
        op_data.operators["冰酿"].current_room = op_data.operators[
            "塑心"
        ].current_room = op_data.operators["见行者"].current_room = "dormitory_1"

        op_data.operators["红"].current_room = op_data.operators[
            "玛恩纳"
        ].current_room = "dormitory_1"

        op_data.operators["冰酿"].current_index = 0
        op_data.operators["塑心"].current_index = 1
        op_data.operators["红"].current_index = 2
        op_data.operators["见行者"].current_index = 3
        op_data.operators["玛恩纳"].current_index = 4
        # drom 2
        op_data.operators["琴柳"].current_room = op_data.operators[
            "阿米娅"
        ].current_room = "dormitory_2"
        op_data.operators["琴柳"].current_index = 0
        op_data.operators["阿米娅"].current_index = 1
        # drom 3
        op_data.operators["迷迭香"].current_room = op_data.operators[
            "杜林"
        ].current_room = op_data.operators["月见夜"].current_room = "dormitory_3"
        op_data.operators["迷迭香"].current_index = 0
        op_data.operators["杜林"].current_index = 1
        op_data.operators["月见夜"].current_index = 2

        return op_data


class TestShiftOnSafety(unittest.TestCase):
    def test_calculate_shift_on_mood_uses_runtime_threshold_and_buffer(self):
        self.assertAlmostEqual(calculate_shift_on_mood(0, 24, 0.65), 17.6)
        self.assertAlmostEqual(calculate_shift_on_mood(0, 24, 0.70), 18.8)
        self.assertAlmostEqual(calculate_shift_on_mood(12, 24, 0.65), 21.8)
        self.assertEqual(calculate_shift_on_mood(0, 24, 2), 24)
        self.assertEqual(calculate_shift_on_mood(0, 24, -1), 2)

    def test_estimate_mood_ready_at_interpolates_from_stable_observation(self):
        observed_at = datetime(2026, 7, 21, 10, 0)
        now = observed_at + timedelta(minutes=5)
        full_at = datetime(2026, 7, 21, 17, 0)

        ready_at = estimate_mood_ready_at(
            now=now,
            observed_at=observed_at,
            observed_mood=10,
            full_at=full_at,
            target_mood=17.6,
            upper_limit=24,
        )

        self.assertEqual(ready_at, datetime(2026, 7, 21, 13, 48))

    def test_estimate_mood_ready_at_is_conservative_for_missing_data(self):
        now = datetime(2026, 7, 21, 10, 0)
        full_at = now + timedelta(hours=3)

        self.assertEqual(
            estimate_mood_ready_at(now, None, 10, full_at, 18, 24), full_at
        )
        self.assertEqual(
            estimate_mood_ready_at(now, now, -1, full_at, 18, 24), full_at
        )
        self.assertIsNone(
            estimate_mood_ready_at(now, now, 10, None, 18, 24)
        )
        self.assertEqual(
            estimate_mood_ready_at(now, now, 19, full_at, 18, 24), now
        )

    def test_shift_on_not_before_uses_latest_resting_operator(self):
        now = datetime(2026, 7, 21, 10, 0)
        plan = {
            "central": ["A", "Current", "B"],
            "room_1_2": ["C", "Current", "Current"],
        }
        ready = {
            "A": now + timedelta(hours=1),
            "B": now + timedelta(hours=2),
        }

        self.assertEqual(shift_on_not_before(plan, ready), now + timedelta(hours=2))

    def test_delay_shift_on_tasks_preserves_other_tasks_and_blocks_unknown_eta(self):
        now = datetime(2026, 7, 21, 10, 0)
        shift = SchedulerTask(
            time=now + timedelta(minutes=22),
            task_plan={"central": ["A"]},
            task_type=TaskTypes.SHIFT_ON,
        )
        blocked = SchedulerTask(
            time=now + timedelta(minutes=30),
            task_plan={"meeting": ["B"]},
            task_type=TaskTypes.SHIFT_ON,
        )
        run_order = SchedulerTask(
            time=now + timedelta(minutes=40),
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room_1_1",
        )
        tasks = [shift, blocked, run_order]

        deferred = delay_shift_on_tasks_until_ready(
            tasks,
            {"A": now + timedelta(hours=2)},
            blocked_operators={"B"},
        )

        self.assertEqual(deferred, {"B"})
        self.assertEqual(shift.time, now + timedelta(hours=2))
        self.assertNotIn(blocked, tasks)
        self.assertIn(run_order, tasks)
        self.assertEqual(run_order.time, now + timedelta(minutes=40))

    def test_sanitize_self_correction_never_moves_resting_high_to_work(self):
        plan = {
            "central": ["Resting", "Wrong"],
            "room_1_2": ["Resting", "Current"],
            "dormitory_1": ["Current", "Resting"],
        }

        sanitized = sanitize_self_correction_plan(plan, {"Resting"})

        self.assertEqual(sanitized["central"], ["Current", "Wrong"])
        self.assertNotIn("room_1_2", sanitized)
        self.assertEqual(sanitized["dormitory_1"], ["Current", "Resting"])

    def test_sanitize_self_correction_removes_noop_work_room(self):
        plan = {
            "room_1_2": ["Current", "Ulpianus", "Andreana"],
            "central": ["Wrong", "Current"],
        }
        current_by_room = {
            "room_1_2": ["Proviso", "Ulpianus", "Andreana"],
            "central": ["CurrentOperator", "Other"],
        }

        sanitized = sanitize_self_correction_plan(
            plan,
            set(),
            current_by_room,
        )

        self.assertNotIn("room_1_2", sanitized)
        self.assertEqual(sanitized["central"], ["Wrong", "Current"])

    def test_plan_metadata_clamps_group_to_latest_safe_mood_time(self):
        now = datetime.now()
        first = Operator(
            "A",
            "central",
            index=0,
            group="group",
            current_room="dormitory_1",
            mood=10,
            upper_limit=24,
            lower_limit=0,
            operator_type="high",
            time_stamp=now,
        )
        second = Operator(
            "B",
            "room_1_2",
            index=0,
            group="group",
            current_room="dormitory_2",
            mood=8,
            upper_limit=24,
            lower_limit=0,
            operator_type="high",
            time_stamp=now,
        )
        working = MagicMock()
        working.is_high.return_value = True
        working.is_resting.return_value = False
        working.room = "meeting"
        working.lower_limit = 0
        working.current_mood.return_value = 0
        working.predict_exhaust.return_value = now

        first_dorm = Dormitory(("dormitory_1", 0), "A", now + timedelta(hours=2))
        second_dorm = Dormitory(("dormitory_2", 0), "B", now + timedelta(hours=3))
        op_data = MagicMock()
        op_data.operators = {"A": first, "B": second, "W": working}
        op_data.dorm = [first_dorm, second_dorm]
        op_data.groups = {"group": ["A", "B"]}
        op_data.plan = {"central": [None], "room_1_2": [None]}
        op_data.config.resting_threshold = 0.7
        op_data.config.free_room = False
        op_data.power_plant_count = 2
        run_order = SchedulerTask(
            time=now + timedelta(hours=1),
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room_2_1",
        )

        tasks = plan_metadata(op_data, [run_order])

        shift_on = next(task for task in tasks if task.type == TaskTypes.SHIFT_ON)
        expected = now + timedelta(hours=3) * ((18.8 - 8) / (24 - 8))
        self.assertAlmostEqual(
            (shift_on.time - expected).total_seconds(),
            0,
            delta=0.1,
        )
        self.assertIn(run_order, tasks)
        self.assertEqual(run_order.time, now + timedelta(hours=1))

    def test_fixed_dorm_operator_is_not_a_shift_on_candidate(self):
        now = datetime(2026, 7, 21, 10, 0)
        fixed = Operator(
            "菲亚梅塔",
            "dormitory_1",
            current_room="dormitory_1",
            current_index=0,
            mood=10,
            operator_type="high",
            time_stamp=now,
        )
        op_data = MagicMock()
        op_data.operators = {"菲亚梅塔": fixed}
        op_data.dorm = []
        op_data.config.resting_threshold = 0.7

        ready, blocked = collect_shift_on_readiness(op_data, now)

        self.assertEqual(ready, {})
        self.assertEqual(blocked, set())

    def test_missing_eta_schedules_retry_then_recovers_shift_on(self):
        now = datetime.now()
        first = Operator(
            "A",
            "central",
            index=0,
            group="group",
            current_room="dormitory_1",
            current_index=0,
            mood=10,
            operator_type="high",
            time_stamp=now,
        )
        second = Operator(
            "B",
            "room_1_2",
            index=0,
            group="group",
            current_room="dormitory_2",
            current_index=0,
            mood=10,
            operator_type="high",
            time_stamp=now,
        )
        first_dorm = Dormitory(("dormitory_1", 0), "A", None)
        second_dorm = Dormitory(("dormitory_2", 0), "B", now + timedelta(hours=2))
        op_data = MagicMock()
        op_data.operators = {"A": first, "B": second}
        op_data.dorm = [first_dorm, second_dorm]
        op_data.groups = {"group": ["A", "B"]}
        op_data.plan = {"central": [None], "room_1_2": [None]}
        op_data.config.resting_threshold = 0.7
        op_data.config.free_room = False
        op_data.power_plant_count = 2

        tasks = plan_metadata(op_data, [])

        self.assertFalse(any(task.type == TaskTypes.SHIFT_ON for task in tasks))
        retry = next(task for task in tasks if task.type == TaskTypes.NOT_SPECIFIC)
        self.assertEqual(shift_on_readiness_retry_names(retry.meta_data), ["A"])
        retry_time = retry.time
        first.current_room = ""
        tasks = plan_metadata(op_data, tasks)
        retry = next(task for task in tasks if task.type == TaskTypes.NOT_SPECIFIC)
        self.assertEqual(retry.time, retry_time)
        self.assertEqual(shift_on_readiness_retry_names(retry.meta_data), ["A"])
        self.assertFalse(any(task.type == TaskTypes.SHIFT_ON for task in tasks))

        first_dorm.time = now + timedelta(hours=3)
        tasks = plan_metadata(op_data, tasks)

        self.assertTrue(any(task.type == TaskTypes.SHIFT_ON for task in tasks))
        self.assertFalse(
            any(shift_on_readiness_retry_names(task.meta_data) for task in tasks)
        )

    def test_single_and_full_group_missing_eta_each_schedule_one_retry(self):
        now = datetime.now()
        for grouped in [False, True]:
            with self.subTest(grouped=grouped):
                names = ["A", "B"] if grouped else ["A"]
                operators = {}
                dorms = []
                plan = {}
                for index, name in enumerate(names):
                    room = "central" if index == 0 else "room_1_2"
                    dorm_room = f"dormitory_{index + 1}"
                    operators[name] = Operator(
                        name,
                        room,
                        index=0,
                        group="group" if grouped else "",
                        current_room=dorm_room,
                        current_index=0,
                        mood=10,
                        operator_type="high",
                        time_stamp=now,
                    )
                    dorms.append(Dormitory((dorm_room, 0), name, None))
                    plan[room] = [None]
                op_data = MagicMock()
                op_data.operators = operators
                op_data.dorm = dorms
                op_data.groups = {"group": names} if grouped else {}
                op_data.plan = plan
                op_data.config.resting_threshold = 0.7
                op_data.config.free_room = False
                op_data.power_plant_count = 2

                tasks = plan_metadata(op_data, [])

                self.assertFalse(
                    any(task.type == TaskTypes.SHIFT_ON for task in tasks)
                )
                retries = [
                    task
                    for task in tasks
                    if shift_on_readiness_retry_names(task.meta_data)
                ]
                self.assertEqual(len(retries), 1)
                self.assertEqual(
                    set(shift_on_readiness_retry_names(retries[0].meta_data)),
                    set(names),
                )


class TestReleaseDormHardening(unittest.TestCase):
    def test_expired_low_priority_bed_uses_resident_type_not_stale_loop_value(self):
        resident = Operator(
            "Resident",
            "",
            current_room="dormitory_1",
            current_index=0,
            mood=24,
            upper_limit=24,
            operator_type="low",
        )
        waiting = Operator(
            "Waiting",
            "",
            current_room="",
            mood=6,
            upper_limit=24,
            lower_limit=0,
            operator_type="low",
        )
        high_last = Operator(
            "HighLast",
            "central",
            current_room="central",
            mood=20,
            operator_type="high",
        )
        op_data = MagicMock()
        op_data.config.free_room = True
        op_data.config.free_blacklist = []
        op_data.operators = {
            "Resident": resident,
            "Waiting": waiting,
            "HighLast": high_last,
        }
        op_data.dorm = [
            Dormitory(
                ("dormitory_1", 0),
                "Resident",
                datetime.now() - timedelta(minutes=1),
            )
        ]
        tasks = []

        try_add_release_dorm({}, None, op_data, tasks)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(
            tasks[0].plan,
            {"dormitory_1": ["Waiting", "Current", "Current", "Current", "Current"]},
        )

    def test_expired_high_priority_resident_is_not_released(self):
        resident = Operator(
            "Resident",
            "central",
            current_room="dormitory_1",
            current_index=0,
            mood=24,
            upper_limit=24,
            operator_type="high",
        )
        waiting = Operator(
            "Waiting",
            "",
            current_room="",
            mood=6,
            upper_limit=24,
            lower_limit=0,
            operator_type="low",
        )
        op_data = MagicMock()
        op_data.config.free_room = True
        op_data.config.free_blacklist = []
        op_data.operators = {
            "Resident": resident,
            "Waiting": waiting,
        }
        op_data.dorm = [
            Dormitory(
                ("dormitory_1", 0),
                "Resident",
                datetime.now() - timedelta(minutes=1),
            )
        ]
        tasks = []

        try_add_release_dorm({}, None, op_data, tasks)

        self.assertEqual(tasks, [])
