# Summary
按照要求，拉取最新代码，使用 basedpyright 检查 `src/` 目录的类型错误，分析错误并生成解决方案文档与用户确认，最后修复代码并运行所有回归测试。

# Current State Analysis
当前位于 `main` 分支，代码库 `src/` 目录下包含 106 个 Python 文件，`tests/` 目录下有多个子模块的测试用例存放于 `tests/*/tests` 结构中。当前环境中未安装 basedpyright。

# Proposed Changes
本任务分为以下几个主要步骤执行：

1. **更新代码与安装依赖**
   - 执行 `git checkout main && git pull origin main` 拉取最新代码。
   - 执行 `pip install basedpyright pytest` 安装所需的类型检查工具和测试框架。

2. **扫描与分析**
   - 运行 `basedpyright src/` 进行类型检查。
   - 提取其中的 `error` 级别报错，并结合出问题的源代码进行分析。
   - 在项目根目录生成 `basedpyright_analysis.md`，详细列出每个 error 的出现位置、原因以及建议的修复代码片段。

3. **方案确认**
   - 通过提示或对话框与用户讨论 `basedpyright_analysis.md` 中的解决方案。
   - 根据用户的反馈调整修复方案，直到用户同意。

4. **代码修复与验证**
   - 按照最终确认的方案，修改 `src/` 下对应的 Python 代码。
   - 持续运行 `basedpyright src/` 进行验证，直到报告中的 error 数量降为 0。
   - 运行 `pytest tests/*/tests` 执行所有的回归测试用例，确保修复类型错误时没有破坏现有功能。

# Assumptions & Decisions
- 本次清理仅针对 `error` 级别的问题，`warning` 和 `information` 级别提示若无重大影响不强制要求清零。
- 项目测试文件（如 `test_t4_core.py`）中导入了 `pytest`，因此决定使用 `pytest` 运行回归测试。
- 如果为了修复类型报错需要对核心逻辑进行大幅度重构，会在方案确认阶段与用户明确提出，以避免意外破坏业务逻辑。

# Verification steps
1. 终端执行 `basedpyright src/`，结果需显示 `0 errors`。
2. 终端执行 `pytest tests/*/tests`，结果需显示所有的测试用例全部 passed。