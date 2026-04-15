"""
技能与工具层 (Skill Hub) 模块入口。

P0.5 T3 阶段：内部已重组至子目录，本文件只从新路径聚合导出。
"""
from .bootstrap import initialize
from .builtin_tools.browser_use import BrowserUsePyTool
from .core.capability_hub import ModelCapabilityRouter, RegisteredCapabilityHub, register_pytools
from .contracts import PyTool, PyToolDefinition
from .exports import SkillHubExports
from .core.tool_parser import parse_doxygen_to_json_schema

__all__ = [
    "BrowserUsePyTool",
    "ModelCapabilityRouter",
    "PyTool",
    "PyToolDefinition",
    "RegisteredCapabilityHub",
    "SkillHubExports",
    "initialize",
    "register_pytools",
    "parse_doxygen_to_json_schema",
]
