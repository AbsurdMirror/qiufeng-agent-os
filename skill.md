# Git 历史记录高级操作技巧 (Git History Manipulation Skills)

本文档总结了在代码开发和代码审查（Code Review）过程中，为了保持 Git 提交记录整洁、干净而常用的一系列高级 Git 操作技巧。

> **⚠️ 核心警告**：
> 下述所有操作都会**修改本地的 Git 提交历史**。如果这些提交已经推送到了远程仓库，在执行完修改操作后，都必须使用 `git push --force origin HEAD` 进行强制推送，以覆盖远程仓库的历史记录。在多人协作的公共分支（如 `main` 或 `master`）上请谨慎使用。

---

## 1. 合并多个连续的提交为一个 (Squash Commits)

**场景**：在开发过程中，为了保存进度生成了多个零碎的提交（如 `fix 1`, `update`, `wip`），在提 PR 前希望把它们合并成一个完整且带有规范描述的提交。

**操作步骤**：
```bash
# 1. 找到这批零碎提交发生【之前】的那次正确提交的 Hash 值（例如 c70c638a）
# 使用 --soft 会撤销这期间的所有 commit 记录，但保留所有代码改动在暂存区（Staged）
git reset --soft c70c638a

# 2. 重新进行一次干净的提交，并附上规范的 Commit Message
git commit -m "feat: 完整的规范功能描述"

# 3. 强制推送到远程
git push --force origin HEAD
```

---

## 2. 从最新的提交中移除多余文件

**场景**：刚做完一次 `git commit`，突然发现不小心把不需要的文件（如自动生成的 `.md` 计划文件、本地配置文件）也包含进去了，希望把这个文件从本次提交中剔除，但不撤销其他代码的改动。

**操作步骤**：
```bash
# 1. 将不需要的文件从 Git 的暂存区/索引中移除（但保留本地磁盘上的物理文件）
git rm --cached <文件路径>
# 例如：git rm --cached .trae/documents/plan.md

# 2. 使用 --amend 修改上一次提交，--no-edit 表示保持原有的 Commit Message 不变
git commit --amend --no-edit

# 3. 强制推送到远程
git push --force origin HEAD
```

---

## 3. 彻底删除最顶端/最新的错误提交

**场景**：远程或本地的最新一次提交完全是错误的（例如某个自动化脚本生成了不需要的提交），我们希望彻底丢弃这个提交，把分支状态回退到上一个干净的节点。

**操作步骤**：
```bash
# 1. 使用 --hard 模式硬重置，直接将 HEAD 指针后退到目标提交，丢弃工作区和暂存区的所有多余改动
git reset --hard <目标正确的Commit Hash>
# 例如回退到上一次提交：git reset --hard HEAD~1

# 2. 强制推送到远程，抹掉远程仓库上的那个最新错误提交
git push --force origin HEAD
```

---

## 4. 修改最新提交的作者信息 (Author)

**场景**：发现刚才提交的 Author 名字或邮箱不对（例如机器代理使用了默认邮箱，或本地 Git config 配置错了），希望修改为正确的名字，以保证贡献者图谱统计正确。

**操作步骤**：
```bash
# 1. 使用 --amend 和 --author 参数直接覆盖最新提交的作者信息
git commit --amend --author="正确的名字 <正确的邮箱@example.com>" --no-edit
# 例如：git commit --amend --author="trae-solo <trae-solo@example.com>" --no-edit

# 2. 因为提交元数据发生了变化（Commit Hash 会变），需要强制推送到远程
git push --force origin HEAD
```

---

## 💡 总结流

在代理助手（Agent）协助开发的模式下，通常的最佳实践流水线是：
1. Agent 自动写代码并产生多次细碎的提交。
2. 开发完成并验证通过后，执行 `git reset --soft` 将提交压扁（Squash）。
3. 检查文件清单，如果有 Agent 生成的额外计划文件，执行 `git rm --cached` + `git commit --amend` 剔除。
4. 如果 Author 信息需要统一，执行 `git commit --amend --author="..."`。
5. 最后执行一次统一的 `git push --force` 完成极其纯净的 PR 交付。