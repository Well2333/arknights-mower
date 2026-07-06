<script setup>
import { storeToRefs } from 'pinia'
import { NTag } from 'naive-ui'
import { h, ref, watch } from 'vue'
import { useConfigStore } from '@/stores/config'

const store = useConfigStore()
const { maa_weekly_plan, maa_weekly_plan1, maa_weekly_plan_active, maa_enable } = storeToRefs(store)

const currentDay = ref(new Date().getDay())
const daysOfWeek = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

const rowStages = (row) =>
  (Array.isArray(row.stage) ? row.stage : [row.stage]).filter((s) => typeof s === 'string')

function syncStagesToWeeklyPlan() {
  maa_weekly_plan.value.slice(0, daysOfWeek.length).forEach((p, i) => {
    const stages = maa_weekly_plan1.value
      .filter((row) => row[daysOfWeek[i]] === 2)
      .flatMap(rowStages)
    p.stage = [...new Set(stages)]
  })
}

// 从当前激活方案反推表格勾选状态：某行全部关卡都在当天方案中则视为“打”
function reconcileFromWeeklyPlan() {
  daysOfWeek.forEach((day, i) => {
    const plan = maa_weekly_plan.value[i]
    const dayStages = new Set(Array.isArray(plan?.stage) ? plan.stage : [])
    maa_weekly_plan1.value.forEach((row) => {
      if (row[day] === 0) {
        return
      }
      const stages = rowStages(row)
      const checked = stages.length > 0 && stages.every((s) => dayStages.has(s))
      row[day] = checked ? 2 : 1
    })
  })
}

watch(maa_weekly_plan_active, () => reconcileFromWeeklyPlan(), { immediate: true })

const togglePlanAndStage = (plan, day) => {
  plan[day] = plan[day] === 1 ? 2 : 1
  syncStagesToWeeklyPlan()
}

const togglePlan = (plan) => {
  let kai = 0
  let guan = 0
  daysOfWeek.forEach((day) => {
    if (plan[day] === 1) {
      guan = guan + 1
    } else if (plan[day] === 2) {
      kai = kai + 1
    }
  })
  daysOfWeek.forEach((day) => {
    if (plan[day] > 0) {
      if (kai > guan) {
        plan[day] = 1
      } else {
        plan[day] = 2
      }
    }
  })
  syncStagesToWeeklyPlan()
}

const changestage = (plan, newstage) => {
  plan['stage'] = newstage
  syncStagesToWeeklyPlan()
}

const stageDisplayNames = {
  '': '上次作战',
  Annihilation: '当期剿灭',
  'LS-6': '经验书',
  'CE-6': '龙门币',
  'AP-5': '红票',
  'SK-5': '碳条',
  'CA-5': '技能书',
  'PR-A-2': '重装医疗2',
  'PR-B-2': '狙击术士2',
  'PR-C-2': '先锋辅助2',
  'PR-D-2': '近卫特种2',
  'PR-A-1': '重装医疗1',
  'PR-B-1': '狙击术士1',
  'PR-C-1': '先锋辅助1',
  'PR-D-1': '近卫特种1',
  '1-7': '1-7'
}

const showstage = (stage) => {
  if (Array.isArray(stage)) {
    return stage.map(showstage).join(', ')
  }
  if (stage in stageDisplayNames) {
    return stageDisplayNames[stage]
  }
  return stage
}

function render_tag({ option, handleClose }) {
  return h(
    NTag,
    {
      type: option.type,
      closable: true,
      onMousedown: (e) => {
        e.preventDefault()
      },
      onClose: (e) => {
        e.stopPropagation()
        handleClose()
      }
    },
    {
      default: () => {
        if (option.label == '') {
          return '上次作战'
        } else if (option.label == 'Annihilation') {
          return '当期剿灭'
        } else if (option.label.endsWith('-HARD')) {
          return option.label.slice(0, -5) + '磨难'
        } else if (option.label.endsWith('-NORMAL')) {
          return option.label.slice(0, -7) + '标准'
        } else {
          return option.label
        }
      }
    }
  )
}

function create_tag(label) {
  const trimmed = label.trim()
  if (trimmed == '' || trimmed == '上次作战') {
    return {
      label: '上次作战',
      value: ''
    }
  } else if (trimmed == '当期剿灭') {
    return {
      label: '当期剿灭',
      value: 'Annihilation'
    }
  } else if (trimmed.endsWith('磨难') || trimmed.endsWith('困难')) {
    return {
      label: trimmed,
      value: trimmed.slice(0, -2) + '-HARD'
    }
  } else if (trimmed.endsWith('标准')) {
    return {
      label: trimmed,
      value: trimmed.slice(0, -2) + '-NORMAL'
    }
  } else {
    return {
      label: trimmed,
      value: trimmed
    }
  }
}

const 默认 = [
  {
    stage: 'Annihilation',
    周一: 1,
    周二: 1,
    周三: 1,
    周四: 1,
    周五: 1,
    周六: 1,
    周日: 1
  },
  {
    stage: '',
    周一: 1,
    周二: 1,
    周三: 1,
    周四: 1,
    周五: 1,
    周六: 1,
    周日: 1
  },
  {
    stage: ['点x删除'],
    周一: 1,
    周二: 1,
    周三: 1,
    周四: 1,
    周五: 1,
    周六: 1,
    周日: 1
  },
  {
    stage: ['把鼠标放到问号上查看帮助'],
    周一: 1,
    周二: 1,
    周三: 1,
    周四: 1,
    周五: 1,
    周六: 1,
    周日: 1
  },
  {
    stage: ['自定义关卡3'],
    周一: 1,
    周二: 1,
    周三: 1,
    周四: 1,
    周五: 1,
    周六: 1,
    周日: 1
  },
  {
    stage: '1-7',
    周一: 1,
    周二: 1,
    周三: 1,
    周四: 1,
    周五: 1,
    周六: 1,
    周日: 1
  },
  {
    stage: 'LS-6',
    周一: 1,
    周二: 1,
    周三: 1,
    周四: 1,
    周五: 1,
    周六: 1,
    周日: 1
  },
  {
    stage: 'CE-6',
    周一: 0,
    周二: 1,
    周三: 0,
    周四: 1,
    周五: 0,
    周六: 1,
    周日: 1
  },
  {
    stage: 'AP-5',
    周一: 1,
    周二: 0,
    周三: 0,
    周四: 1,
    周五: 0,
    周六: 1,
    周日: 1
  },
  {
    stage: 'SK-5',
    周一: 1,
    周二: 0,
    周三: 1,
    周四: 0,
    周五: 1,
    周六: 1,
    周日: 0
  },
  {
    stage: 'CA-5',
    周一: 0,
    周二: 1,
    周三: 1,
    周四: 0,
    周五: 1,
    周六: 0,
    周日: 1
  },
  {
    stage: 'PR-A-2',
    周一: 1,
    周二: 0,
    周三: 0,
    周四: 1,
    周五: 1,
    周六: 0,
    周日: 1
  },
  {
    stage: 'PR-A-1',
    周一: 1,
    周二: 0,
    周三: 0,
    周四: 1,
    周五: 1,
    周六: 0,
    周日: 1
  },
  {
    stage: 'PR-B-2',
    周一: 1,
    周二: 1,
    周三: 0,
    周四: 0,
    周五: 1,
    周六: 1,
    周日: 0
  },
  {
    stage: 'PR-B-1',
    周一: 1,
    周二: 1,
    周三: 0,
    周四: 0,
    周五: 1,
    周六: 1,
    周日: 0
  },
  {
    stage: 'PR-C-2',
    周一: 0,
    周二: 0,
    周三: 1,
    周四: 1,
    周五: 0,
    周六: 1,
    周日: 1
  },
  {
    stage: 'PR-C-1',
    周一: 0,
    周二: 0,
    周三: 1,
    周四: 1,
    周五: 0,
    周六: 1,
    周日: 1
  },
  {
    stage: 'PR-D-2',
    周一: 0,
    周二: 1,
    周三: 1,
    周四: 0,
    周五: 0,
    周六: 1,
    周日: 1
  },
  {
    stage: 'PR-D-1',
    周一: 0,
    周二: 1,
    周三: 1,
    周四: 0,
    周五: 0,
    周六: 1,
    周日: 1
  }
]

function clear() {
  maa_weekly_plan1.value = JSON.parse(JSON.stringify(默认))
  reconcileFromWeeklyPlan()
}
</script>

<template>
  <n-card>
    <n-checkbox v-model:checked="maa_enable" class="card-title">刷理智周计划·新</n-checkbox>

    <help-text>
      <div>先看上一个周计划问号</div>
      <div>此表格与上方“刷理智周计划”共用数据：点“打”会把该行关卡写入对应日期的关卡列表。</div>
      <div>切换周计划方案后，表格会根据新方案自动更新勾选状态。</div>
      <div>如何不打本：<b>把所有的"打"都点了</b>或者点一次<b>清除当前配置以匹配最新表格</b></div>
      <div>建议每次更新后 点一次<b>清除当前配置以匹配最新表格</b></div>
      <div>如果觉得这个表有什么要改进的 at群管理</div>
      <div>中间三行的空行用来写 一些自定义关卡</div>
      <div>
        新用法<n-tag closable>SSReopen-XX</n-tag> 如<n-tag closable>SSReopen-FC</n-tag
        >可以刷照我以火的所有复刻本(FC-1到FC-8)
      </div>
      <ul>
        <li>
          在自定义行填入<n-tag closable class="tag-mr">HE-7</n-tag>

          下一行填入<n-tag closable>1-7</n-tag>

          则会刷活动关HE-7，若活动未开放，则刷1-7。
        </li>
        <li><n-tag closable>12-17标准</n-tag> 表示12-17标准难度。</li>
        <li><n-tag closable>12-17磨难</n-tag> 表示12-17磨难难度。</li>
        <li><b>当期剿灭</b>：输入“当期剿灭”后回车，生成 <n-tag closable>当期剿灭</n-tag> 标签。</li>
        <li>
          <b>信用作战</b>：若信用作战选项已开启，且当日计划不包含
          <n-tag closable>上次作战</n-tag>，则自动进行信用作战。
        </li>
      </ul>
    </help-text>

    <n-popconfirm @positive-click="clear">
      <template #trigger>
        <n-button>清除当前配置以匹配最新表格</n-button>
      </template>
      将表格恢复为默认布局（不会修改各日期已配置的关卡），确定？
    </n-popconfirm>
    <div class="tasktable">
      <table size="small" :single-column="true" :single-line="true">
        <thead>
          <tr>
            <th>全选</th>
            <th>关卡</th>
            <th v-for="(day, index) in daysOfWeek" :key="index">
              {{ day[1] }}{{ currentDay === (index + 1) % 7 ? ' (今天)' : '' }}
            </th>
          </tr>
          <tr>
            <th></th>
            <th>药</th>
            <th v-for="(day, index) in daysOfWeek" :key="index">
              <n-input-number
                v-if="maa_weekly_plan[index]"
                v-model:value="maa_weekly_plan[index].medicine"
                :min="0"
                :max="999"
                :show-button="false"
              />
            </th>
          </tr>
          <tr>
            <th></th>
            <th>理智</th>
            <th v-for="(day, index) in daysOfWeek" :key="index">
              <n-input-number
                v-if="maa_weekly_plan[index]"
                v-model:value="maa_weekly_plan[index].sanity_threshold"
                :min="0"
                :max="210"
                :show-button="false"
              />
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(plan, index) in maa_weekly_plan1" :key="index">
            <td>
              <n-button
                @click="() => togglePlan(plan)"
                quaternary
                style="width: 100%; height: 100%"
                class="class1"
              ></n-button>
            </td>
            <td>
              <n-select
                v-if="index > 1 && index < 5"
                v-model:value="plan.stage"
                multiple
                filterable
                tag
                :show="false"
                :show-arrow="false"
                :render-tag="render_tag"
                :on-create="create_tag"
                @update:value="(value) => changestage(plan, value)"
              />
              <span v-else>{{ showstage(plan.stage) }}</span>
            </td>
            <td
              v-for="day in daysOfWeek"
              :key="day"
              :class="{ class2: plan[day] === 2, class1: plan[day] === 1 }"
            >
              <template v-if="plan[day] !== 0">
                <n-button
                  @click="() => togglePlanAndStage(plan, day)"
                  quaternary
                  style="width: 100%; height: 100%"
                >
                  <span v-if="plan[day] === 2">打</span>
                  <span v-if="plan[day] === 1"></span>
                </n-button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </n-card>
</template>

<style scoped lang="scss">
@media screen and (max-width: 1399px) {
  .tasktable {
    height: 300px;
    overflow-y: auto;
  }

  .tasktable table {
    border-collapse: collapse;
  }

  .tasktable td:first-child {
    width: 10%;
  }

  .tasktable td:nth-child(2) {
    width: 18%;
  }

  .tasktable td:not(:first-child):not(:nth-child(2)) {
    width: calc(72% / 7);
  }

  .tasktable thead {
    position: sticky;
    top: 0;
    background-color: hsl(196, 26%, 60%);
    z-index: 1;
  }
}

@media screen and (min-width: 1400px) {
  .tasktable {
    height: auto;
  }

  .tasktable table {
    border-collapse: collapse;
  }

  .tasktable td:first-child {
    width: 10%;
  }

  .tasktable td:nth-child(2) {
    width: 18%;
  }

  .tasktable td:not(:first-child):not(:nth-child(2)) {
    width: calc(72% / 7);
  }

  .tasktable thead {
    background-color: hsl(196, 26%, 60%);
  }
}

.class1 {
  background-color: hsl(33, 30%, 91%);
  text-align: center;
  vertical-align: middle;
}

.class2 {
  background-color: hsl(200, 90%, 65%);
  text-align: center;
  vertical-align: middle;
}
</style>
