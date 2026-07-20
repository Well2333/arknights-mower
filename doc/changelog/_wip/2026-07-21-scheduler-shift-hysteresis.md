---
date: 2026-07-21
branch: fix/scheduler-shift-hysteresis
merge_commit: pending
type: fix
scope: 基建排班调度
guideline_changed: true
---

# 阻止低心情工作组短周期回班振荡

## 做了什么

- 按运行时 `resting_threshold` 和 `+2` 心情缓冲计算安全回班门槛，并对完整动态休息组取最晚就绪时间；最终钳制覆盖急救与既有提前路径。
- `SELF_CORRECTION` 统一清洗宿舍主力和位置未知的分组主力，只保留普通错位纠正；清洗后为空则不创建任务。
- 菲亚梅塔只允许无分组目标提前回班；任何已分组目标保持原安全 `SHIFT_ON` 时间。
- ETA 缺失时创建幂等的专用宿舍重读任务；固定宿舍岗被排除，扫描异常或 OCR 漏识别不会执行不安全回班或形成逾期紧循环。

## 验证

- 四个修改文件本地 `py_compile` 与 `git diff --check` 通过。
- Windows 隔离 staging：`TestShiftOnSafety` 10 项、`TestSchedulerStability` 6 项、原 scheduler 模块 33 项、原 BaseScheduler 9 项、MergeRunOrder 5 项均通过。
- 全项目 73 项中 72 项通过；唯一错误是实例 `9a872fbc` 的 `simulate()` 不支持开发分支既有 `startup_maa_check` 测试参数，与本修复无关，已单独记录为基线版本差异。
- 历史序列的线上 90 分钟/2 小时回放仍属于部署后的灰度门禁，尚未宣告通过。
- 运行实例精确候选回归 32/32、20/20 通过；源码备份和哈希校验后已部署。重计时的 T+10 冒烟通过：PM2/WebUI/调度在线，未来任务队列正常，无异常换班、自纠正、ERROR 或重读紧循环；90 分钟及后续灰度门禁仍继续观察。

## 为什么

实例记录显示，当前全局急救时间会把组休息截短到约 30 分钟，任务生成还可能再提前 8 分钟；低心情组回班后 1～6 分钟便再次下班。纠错和菲亚路径还可以绕过普通回班任务。

## 影响的文件 / 范围

- `arknights_mower/utils/scheduler_task.py`
- `arknights_mower/solvers/base_schedule.py`
- `arknights_mower/tests/scheduler_task_tests.py`
- `arknights_mower/tests/base_scheduler_tests.py`
- `doc/guidelines/scheduler-stability.md`

## 注意事项 / 后续

- 首批不修改 `plan.json`、配置模型、数据库或任务序列化格式。
- 代码稳定 24 小时后，才单独验证会客室专用替补和移除多人组菲亚目标的配置候选。

## 规范同步

- 新增 `doc/guidelines/scheduler-stability.md`：明确 dorm→work 的任务边界、心情滞回公式、组就绪规则、测试及灰度回滚门禁。
