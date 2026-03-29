# P0 T3 能力接入与转发 (Capability Access) 审阅报告

## 审阅概述
本次审阅针对 T3 阶段“能力接入与转发”的核心目标进行检查，重点关注编排层统一 Capability 契约的建立、Skill Hub 模块的引入、LiteLLM 归一化逻辑以及 MiniMax 模型适配等改动。整体架构实现了良好的隔离与优雅降级。

## P0 级建议与结论（核心阻断/架构级调整）
- [ ] **全局模型兜底硬编码**：在 `src/model_provider/minimax.py` 的 `_resolve_minimax_target_model_name` 函数中，硬编码回退到了 `"abab6.5s-chat"` 模型。如果该模型未来下线，修改代码成本较高且容易引发线上故障。建议：将这种全局兜底模型名称提取到统一的环境变量或系统配置文件中进行管理。

## P1 级建议与结论（重要功能/体验优化）
- [ ] **完善工具环境探测逻辑**：在 `src/skill_hub/browser_use.py` 的 `probe_browser_use_runtime` 中，目前仅探测了 `browser_use` 和 `playwright` 两个 Python 包是否通过 pip 安装，但未能检查底层浏览器二进制文件（如通过 `playwright install` 下载的 Chromium）是否就绪。建议补充执行或检测对应浏览器驱动的环境探测，避免运行时闪退。

## P2 级建议与结论（边缘优化/代码规范）
*暂无。*
