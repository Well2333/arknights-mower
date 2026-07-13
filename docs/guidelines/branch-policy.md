# 分支与上游同步政策

## 权威分支

- `dev-custom` 是本仓库唯一的开发及实际使用主线，与官方 `upstream` 分支明确区分。
- 所有自定义代码、配置、文档、规范、上游合并结果及发布候选只能提交到
  `dev-custom`。
- 开始任何写操作前必须确认当前分支为 `dev-custom`；不得为自定义工作创建功能、
  修复或临时分支。

## 受保护的上游镜像分支

- `dev`、`main` 及其他非 `dev-custom` 分支不得承载任何自定义修改，也不得作为发布
  来源。
- 非自定义分支必须与官方 `upstream` 的对应分支保持一致；本地只允许通过
  fast-forward 更新为对应的 `upstream/<branch>`，不得在其上提交、合并、rebase 或
  cherry-pick 自定义改动。
- 没有对应 upstream 分支的临时本地分支应删除，避免被误用为开发或发布来源。

## 上游同步流程

1. 从 `upstream` fetch 最新引用，不在非自定义分支上开发。
2. 将 `upstream/dev` 合并进 `dev-custom`，保留本仓库自定义功能并人工解决冲突。
3. 同步后在 `dev-custom` 上完成测试、版本标识和变更记录收敛。
4. 如需同步本地镜像分支，只将其 fast-forward 到对应 upstream 引用。

## 发布限制

- 严禁从 `dev-custom` 之外的任何分支构建或执行发布。
- 即使来源为 `dev-custom`，`git push`、tag、Release、发布包等远程或对外操作仍需
  用户在当次任务中明确授权。
