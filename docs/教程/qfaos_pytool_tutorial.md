# QFAOS 框架 PyTool 注册与使用教程

在 QFAOS (Qiufeng Agent OS) 框架中，**PyTool** 是一种将 Python 函数/方法暴露给大模型（LLM）作为工具（Skill/Capability）调用的核心机制。为了确保类型安全与自动化的大模型 Schema 推导，QFAOS 提供了三种灵活的工具注册方式。

本教程将详细讲解如何定义、注册并使用 PyTool，以及在不同规模项目中的适用场景对比。

---

## 核心规范 (必读)

无论使用哪种注册方式，定义的工具函数**必须**遵循以下严格规范。QFAOS 底层会通过这些信息自动生成给大模型理解的 JSON Schema：

1. **类型注解与描述**：所有的参数和返回值必须使用 `typing.Annotated` 和 `pydantic.Field` 提供明确的类型和描述（description）。
2. **函数文档（Docstring）**：必须提供函数的 docstring，作为工具的整体功能描述。

> ⚠️ **警告**：如果未按照规范使用 `Annotated[...]` 进行标记，注册时 QFAOS 将直接抛出 `TypeError` 异常并阻断启动。

### 标准结构示例：
```python
from typing import Annotated
from pydantic import Field

def my_tool(
    a: Annotated[int, Field(description="参数 A 的用途说明")]
) -> Annotated[int, Field(description="返回值的用途说明")]:
    """这里是工具的整体描述，大模型会根据这段话判断何时使用该工具。"""
    return a
```

---

## 注册方式详解

### 方式一：使用 `@agent.pytool` 装饰器 (极简模式)

这是最简单、直接的注册方式。通过 `agent` 实例的 `pytool` 装饰器，可以在定义函数的同时自动完成注册，做到“即插即用”。

- **适用场景**：单文件脚本、小型 Agent 项目、无需管理复杂状态的独立函数工具。
- **优点**：代码量最少，直观。
- **缺点**：工具代码强依赖于具体的 `agent` 实例对象。

**代码示例**：
```python
from qfaos import QFAOS
from typing import Annotated
from pydantic import Field

agent = QFAOS()

@agent.pytool(id="tool.math.add")
def add_numbers(
    a: Annotated[int, Field(description="第一个加数")],
    b: Annotated[int, Field(description="第二个加数")]
) -> Annotated[int, Field(description="和")]:
    """执行加法运算。"""
    return a + b
```

---

### 方式二：使用 `register_pytool_instance` 注册类实例 (面向对象模式)

在实际工程中，工具通常需要依赖某些外部状态（例如数据库连接、API Token、网络客户端等）。将这些相关工具内聚在一个类中，通过实例化对象进行批量注册，是**最推荐的工程实践**。

- **适用场景**：中大型项目、模块化开发、工具之间需要共享状态。
- **优点**：支持面向对象编程（OOP），能够轻松管理依赖和状态，并且一次性注册整个类中的所有工具。

**代码示例**：
```python
from qfaos import QFAOS, qfaos_pytool
from typing import Annotated
from pydantic import Field

# 1. 定义一个内聚的服务类
class MathService:
    def __init__(self, precision: int = 2):
        self.precision = precision

    # 使用 @qfaos_pytool 标记该方法为工具能力
    @qfaos_pytool(id="tool.math.subtract")
    def subtract(
        self, 
        a: Annotated[int, Field(description="被减数")], 
        b: Annotated[int, Field(description="减数")]
    ) -> Annotated[int, Field(description="差")]:
        """执行减法运算。"""
        return round(a - b, self.precision)

# 2. 实例化并注册
agent = QFAOS()
math_service = MathService(precision=4)

# agent 会自动扫描 math_service 实例中所有被 @qfaos_pytool 装饰的方法并注册
agent.register_pytool_instance(math_service)
```

---

### 方式三：使用 `@qfaos_pytool` + `register_pytool` 手动注册 (解耦模式)

这种方式将工具的**定义**和**注册**完全分离。你可以在领域层（Domain Layer）仅依赖 `@qfaos_pytool` 标记能力，而在应用层（Application Layer）再将其注册到 `agent` 中。

- **适用场景**：严格遵循领域驱动设计（DDD）的大型复杂项目、插件化架构。
- **优点**：极致解耦。业务领域层的代码不需要知道 `agent` 的存在。

**代码示例**：
```python
# 1. 在领域层定义工具 (纯净，不依赖 agent 实例)
from qfaos import qfaos_pytool
from typing import Annotated
from pydantic import Field

@qfaos_pytool(id="tool.math.multiply")
def manual_multiply(
    a: Annotated[int, Field(description="因数 A")], 
    b: Annotated[int, Field(description="因数 B")]
) -> Annotated[int, Field(description="积")]:
    """执行乘法运算。"""
    return a * b

# 2. 在应用入口/编排层组装和手动注册
from qfaos import QFAOS

agent = QFAOS()
agent.register_pytool(manual_multiply)
```

---

## 适用场景对比总结

为了方便开发者快速选择合适的工具注册方式，请参考下表：

| 注册方式 | 代码耦合度 | 状态管理 | 适用项目规模 | 核心特点 |
| :--- | :--- | :--- | :--- | :--- |
| **`@agent.pytool`** | 高 (直接依赖 agent 实例) | 无状态 (纯函数) | 小型脚本 / 快速原型 | 最快捷，声明即注册，适合零散工具 |
| **`register_pytool_instance`** | 低 (方法仅依赖标记装饰器) | 有状态 (依赖类实例属性) | 中大型项目 / 模块化 | 面向对象，适合高内聚的一组同类工具集，支持依赖注入 |
| **`@qfaos_pytool` + `register_pytool`** | 极低 (定义与注册完全分离) | 无状态 (纯函数) | 大型 DDD 项目 / 插件化 | 极致解耦，领域层纯净，控制反转 |

## 常见问题与注意事项

1. **工具 ID 唯一性**：不同工具的 `id`（例如 `tool.math.add`）必须是全局唯一的，它是大模型在底层识别并触发该工具的唯一标识符。如果同名 `id` 被重复注册，新定义的工具会覆盖旧的定义。
2. **异步支持**：PyTool 同时支持同步函数（`def`）和异步函数（`async def`），QFAOS 的底层编排引擎会自动处理相应的执行上下文。
3. **报错 `TypeError: must use Annotated[...]`**：请检查你的函数参数和返回值是否**完全**使用了 `Annotated` 与 `Field` 进行包裹，这是 QFAOS 自动推导大模型参数 Schema 的强制性要求。
