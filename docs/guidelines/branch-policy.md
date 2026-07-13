# 分支与上游同步政策

## 权威分支

- `dev-custom` 是本仓库唯一的开发及实际使用主线，与官方 `upstream` 分支明确区分。
- 所有自定义代码、配置、文档、规范及发布候选最终只能合入 `dev-custom`。
- 日常开发必须遵守 `Agent.md` 的分支要求：从 `dev-custom` 新建带类型前缀的工作
  分支（如 `feat/`、`fix/`、`chore/`、`docs/`），完成后 squash 合并回
  `dev-custom` 并删除工作分支。
- 新建工作分支是允许且必要的；禁止的是在 upstream 已有分支及其本地镜像上进行
  自定义开发。

## 受保护的上游镜像分支

- `dev`、`main`、`clean` 等在官方 upstream 已存在的分支及其本地镜像不得承载任何
  自定义修改，也不得作为发布来源。
- upstream 已有分支的本地镜像必须与官方对应分支保持一致；本地只允许通过
  fast-forward 更新为对应的 `upstream/<branch>`，不得在其上提交、合并、rebase 或
  cherry-pick 自定义改动。
- 自定义工作分支必须以 `dev-custom` 为基线，不得以 upstream 镜像分支为基线；工作
  完成并合入 `dev-custom` 后应按 `Agent.md` 删除。

## 上游同步流程

1. 从 `upstream` fetch 最新引用，不在 upstream 已有分支及其镜像上开发。
2. 从 `dev-custom` 创建 `chore/` 类型的上游同步工作分支，在该分支合并
   `upstream/dev`、保留本仓库自定义功能并人工解决冲突。
3. 验证通过后将同步工作分支以普通 merge 合并回 `dev-custom`，再删除该工作分支；
   为保留 upstream 祖先关系，上游同步是工作分支 squash 规则的唯一例外。
4. 如需同步本地 upstream 镜像分支，只将其 fast-forward 到对应 upstream 引用。

## 发布限制

- 严禁从 `dev-custom` 之外的任何分支执行发布；工作分支只用于开发和验证。
- 即使来源为 `dev-custom`，`git push`、tag、Release、发布包等远程或对外操作仍需
  用户在当次任务中明确授权。
