"""
技能与工具层 (Skill Hub) 模块入口。

设计意图：
作为架构中的能力集线器，这里统一导出了内部的 PyTool 契约、具体的浏览器工具实现，
以及负责将工具和模型统一包装为 Capability 的注册中心（Capability Hub）。
它实现了“外观模式 (Facade)”，让外层（如 app/bootstrap）可以通过这里一站式导入所需的初始化组件。

初学者提示：
`__all__` 列表是 Python 包的“对外承诺”。当你在其他文件写 `from src.skill_hub import *` 时，
只有这个列表里的名字才会被导入，这能有效防止内部的辅助函数污染外部的命名空间。
"""
from .bootstrap import initialize
from .browser_use import BrowserUsePyTool, probe_browser_use_runtime
from .capability_hub import ModelCapabilityRouter, RegisteredCapabilityHub, register_pytools
from .contracts import BrowserUseRuntimeState, PyTool, PyToolDefinition
from .exports import SkillHubExports
from .tool_parser import parse_doxygen_to_json_schema

__all__ = [
    "BrowserUsePyTool",
    "BrowserUseRuntimeState",
    "ModelCapabilityRouter",
    "PyTool",
    "PyToolDefinition",
    "RegisteredCapabilityHub",
    "SkillHubExports",
    "initialize",
    "probe_browser_use_runtime",
    "register_pytools",
]
