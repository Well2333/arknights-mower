---
date: 2026-08-03
branch: fix/scheduler-stability-upstream-20260803
merge_commit: pending
type: fix
scope: 基建排班调度
guideline_changed: true
---

# 同步上游并收敛基建排班功能面

## 做了什么

- 按运行时 `resting_threshold` 和 `+2` 心情缓冲计算安全回班门槛，并对完整动态休息组取最晚就绪时间；最终钳制覆盖急救与既有提前路径。
- `SELF_CORRECTION` 统一清洗宿舍主力和位置未知的分组主力，只保留普通错位纠正；清洗后为空则不创建任务。
- 菲亚梅塔只允许无分组目标提前回班；任何已分组目标保持原安全 `SHIFT_ON` 时间。
- 基于最新 `upstream/dev` 重建修复分支，纳入 MAA 连通性检测与专精计划上游修复。
- 保留 dev-custom 的 `MaaWeeklyNew` 周计划表格，并移除相邻跑单自动合并、可调贴近策略和“推迟其他任务”操作。
- 仅保留最小“立即跑单”按钮/API：唤醒休眠队列、标记最近未来跑单并强制无人机，不改动其他任务。
- `immediate` 状态可随任务缓存跨停止/重启保留；启动和任务唤醒完成后清理事件，避免陈旧信号或丢失唤醒。
- ETA 缺失时创建幂等的专用宿舍重读任务；固定宿舍岗被排除，扫描异常或 OCR 漏识别不会执行不安全回班或形成逾期紧循环。

## 验证

- 本地全量 `compileall` 与 `git diff --check` 通过；本机缺少 `evalidate`、`cv2`，完整单测改在实例 Python 环境执行。
- Windows 隔离 staging 运行 77 项排班/任务/宿舍/OCR/日志/MAA 测试及 2 项立即跑单 API 测试，共 79 项全部通过。
- WebUI 生产构建通过，Vite 完成 6679 个模块转换；自定义界面仅包含“立即跑单”入口与 `MaaWeeklyNew` 周计划表格。
- 提交级和全文审计确认不存在相邻跑单自动合并、推迟任务或 custom 分支策略文件；`MaaWeeklyNew` 仅通过独立配置映射 MAA 周计划，不接触基建任务队列。
- 当前合并分支尚未部署到生产实例；历史 90 分钟/2 小时灰度结果仍有效，部署后需重新观察运行时门禁。

## 为什么

实例记录显示，当前全局急救时间会把组休息截短到约 30 分钟，任务生成还可能再提前 8 分钟；低心情组回班后 1～6 分钟便再次下班。纠错和菲亚路径还可以绕过普通回班任务。

## 影响的文件 / 范围

- `arknights_mower/utils/scheduler_task.py`
- `arknights_mower/solvers/base_schedule.py`
- `arknights_mower/utils/config/__init__.py`
- `arknights_mower/utils/config/conf.py`
- `arknights_mower/utils/csleep.py`
- `arknights_mower/__main__.py`
- `arknights_mower/solvers/record.py`
- `server.py`
- `ui/src/components/MaaWeeklyNew.vue`
- `ui/src/pages/maasettings.vue`
- `ui/src/stores/config.js`
- `ui/components.d.ts`
- `ui/src/pages/Log.vue`
- `arknights_mower/tests/scheduler_task_tests.py`
- `arknights_mower/tests/base_scheduler_tests.py`
- `doc/guidelines/scheduler-stability.md`

## 注意事项 / 后续

- 首批不修改 `plan.json`、数据库或调度任务序列化格式；配置模型只新增与基建调度隔离的 `maa_weekly_plan1` 表格布局字段。
- 代码稳定 24 小时后，才单独验证会客室专用替补和移除多人组菲亚目标的配置候选。

## 规范同步

- 新增 `doc/guidelines/scheduler-stability.md`：明确 dorm→work 的任务边界、心情滞回公式、组就绪规则、测试及灰度回滚门禁。
