"""
skill_hub.core —— Skill Hub 核心框架模块。

包含能力中心、协议定义、工具规范解析器和导出容器。

注意：本 __init__.py 不导入 exports.py，以避免与 builtin_tools 形成循环依赖。
（exports.py 依赖 builtin_tools.browser_use，而 browser_use 又依赖 core.contracts）
上层代码应直接从 src.skill_hub.core.exports 导入 SkillHubExports。
"""
from .capability_hub import ModelCapabilityRouter, RegisteredCapabilityHub
from .contracts import BrowserUseRuntimeState, PyTool, PyToolDefinition
from .tool_parser import parse_doxygen_to_json_schema

__all__ = [
    "BrowserUseRuntimeState",
    "ModelCapabilityRouter",
    "PyTool",
    "PyToolDefinition",
    "RegisteredCapabilityHub",
    "parse_doxygen_to_json_schema",
]
