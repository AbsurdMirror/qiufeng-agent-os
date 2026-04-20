from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CapabilityDescription:
    """
    单个能力的标准化描述对象 (数据类，不可变)。

    设计意图：
    让编排层能够在不感知底层模型或工具实现差异的前提下，
    以统一元数据发现能力的调用入口、输入输出约束与附加属性。
    这就像是一份“说明书”，告诉调用者这个能力是什么、怎么用。
    """
    # 能力的全局唯一标识符，例如 "model.chat.default" 或 "tool.browser.open"
    capability_id: str
    # 能力所属的领域，例如 "model"（模型类）或 "tool"（工具类）
    domain: str
    # 能力的简短名称，用于展示或日志记录
    name: str
    # 能力的详细描述，通常给大模型阅读，以便模型决定是否调用此能力
    description: str
    # 输入参数的 JSON Schema 描述，定义了调用该能力需要传入什么结构的数据
    input_schema: dict[str, Any] = field(default_factory=dict)
    # 输出结果的 JSON Schema 描述，定义了调用该能力会返回什么结构的数据
    output_schema: dict[str, Any] = field(default_factory=dict)
    # 其他附加元数据，例如供应商信息 (provider) 或内部种类 (kind)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CapabilityRequest:
    """
    编排层发起能力调用时的统一请求载体 (数据类，不可变)。
    
    无论调用的是大模型推理，还是浏览器操作工具，都通过这个统一的请求对象进行封装，
    抹平了不同底层组件的调用差异。
    """
    # 想要调用的目标能力的唯一标识符，必须与 CapabilityDescription 中的 id 对应
    capability_id: str
    # 实际调用时传递的参数载荷，其结构应当符合该能力的 input_schema
    payload: dict[str, Any] = field(default_factory=dict)
    # 调用时的附加元数据，可用于传递追踪ID、租户信息等上下文
    metadata: dict[str, Any] = field(default_factory=dict)
    # 当能力执行需要用户审批时，携带用户已批准的票据 ID（用于灰名单放行与核销）
    ticket_id: str | None = None


@dataclass(frozen=True)
class CapabilityResult:
    """
    能力调用的统一返回结构 (数据类，不可变)。
    
    统一了成功和失败的返回格式，方便编排引擎做统一的后置处理和错误检查。
    """
    # 被调用的能力的唯一标识符
    capability_id: str
    # 能力调用是否成功
    success: bool
    # 能力调用成功时的输出结果数据，结构应符合 output_schema
    output: dict[str, Any] = field(default_factory=dict)
    # 错误码，当 success 为 False 时存在
    error_code: str | None = None
    # 错误提示信息，当 success 为 False 时存在
    error_message: str | None = None
    # 结果的附加元数据，可包含执行耗时、消耗 Token 等信息
    metadata: dict[str, Any] = field(default_factory=dict)

