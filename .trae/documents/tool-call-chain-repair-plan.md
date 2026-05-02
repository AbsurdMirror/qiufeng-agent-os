# 工具调用链路修复计划

## Summary

- 目标：以 `litellm/openai` 的消息与工具调用语义为基准，补齐 `src/model_provider` -> `src/qfaos` -> `agents/bill_management_agent.py` -> `src/storage_memory` 整条工具调用链路的数据建模、解析转换、错误处理与记忆落盘。
- 目标：在上述修复中，进一步把 qfaos 和模型层当前分散的模型输入输出契约统一到 `src/domain` 的 `ModelRequest` / `ModelResponse` 上，避免框架层重复定义一套近似但不兼容的模型接口。
- 范围：只处理“模型返回 tool call / content”以及“工具执行结果回传模型”的链路；不扩展新的业务能力，不改渠道层协议，不处理与工具调用无关的模型输出问题。
- 交付标准：
  - 模型层支持一次响应内的多个 `tool_calls`，不再只取第一个。
  - 模型层能同时承载 `assistant.content` 与 `assistant.tool_calls`，不因两者并存而误判失败。
  - tool/content 的格式化与解析失败能返回结构化错误信息，并能区分“可重试修复”和“终止失败”。
  - qfaos 中与模型相关的输入输出接口不再与模型层重复建模，而是基于 `src/domain` 的统一请求/响应对象封装。
  - qfaos 自身数据类型能显式表达 assistant tool call 消息、tool result 消息和最终 answer，而不是继续依赖临时 dict。
  - memory 层可记录 assistant 的 tool calls 以及 tool role 的工具返回消息，并在下轮请求中恢复成可再次发送给 LiteLLM/OpenAI 的消息结构。
  - 这次改动涉及的 Python 代码尽量使用精确类型注解，不用 `Any` 做大兜底；出现非预期类型时直接报错。
  - 面向用户展示的错误信息统一带上错误位置与调用栈摘要，便于后续扩展复用。

## Current State Analysis

### 现有链路

- `src/model_provider/providers/litellm_adapter.py`
  - `build_model_response()` 能从 LiteLLM 响应提取 `content`、`tool_calls`、`usage`。
  - 但内部只把 `message_obj.tool_calls` 转为 `CapabilityRequest` + `ToolInvocation`，未抽象为统一消息片段；同时对解析失败直接返回失败响应，错误上下文较少。
  - 当 `content` 与 `tool_calls` 同时存在时，仅在几个分支中“顺带保留”，没有明确表达“这是一条 assistant 消息，含文本+多个工具调用”的统一语义。

- `src/model_provider/validators/output_parser.py`
  - `convert_litellm_tool_calls()` 已能遍历整个列表，不是只解析第一个；但输出只是 `CapabilityRequest`，缺少与 assistant 消息绑定的一等类型。
  - 仅支持 `ChatCompletionMessageToolCall` 风格对象，兼容旧版 `function_call`、dict-like tool call、参数文本脏数据时的错误上下文不完整。
  - `_parse_tool_arguments()` 失败时只返回通用错误码，无法保留原始 arguments、tool name、索引位置等修复信息。

- `src/domain/models.py`
  - `ModelMessage` 只有 `role/content/tool_calls`，无法表达 `tool` 角色消息所需的 `tool_call_id/name`，也无法表达更完整的 assistant/tool 语义。
  - `ModelResponse` 只区分 `content`、`tool_calls`、`tool_invocations`，缺少“响应消息本体”的统一承载字段，导致 qfaos 和 memory 只能各自猜测如何重建消息。

- `src/qfaos/runtime/contracts.py`
  - `QFAModelOutput` / `QFAToolResult` 与 `src/domain.models.ModelResponse` 并行存在，形成重复接口，且 `QFAModelOutput` 只有单个 `tool_call` 字段，设计上天然只支持一个工具调用。
  - `QFAToolResult` 只表达单个工具执行结果，不能作为“回填给模型的 tool message”直接复用。

- `src/qfaos/runtime/context_facade.py`
  - `_to_model_output()` 明确只取 `output.tool_calls[0]`。
  - `call_pytool()` 只接受单个 `tool_call: dict[str, Any]`。
  - `add_memory()` 只能记录 `content + tool_invocations`，不能记录真正的 `tool` role 消息。
  - `_build_messages()` 仅恢复 `role/content/tool_calls`，无法恢复 `tool_call_id`，这正是历史手工测试里必须绕过 `ModelMessage` 的根因。

- `src/storage_memory/internal/codecs.py` 与 `src/domain/memory.py`
  - 只落盘 `tool_calls`，不记录 tool result message。
  - 反序列化后只能恢复 assistant tool call，不能恢复 `role="tool"` 的消息结构。

- `agents/bill_management_agent.py`
  - AI 主循环以 `model_output.is_pytool_call` + 单个 `model_output.tool_call` 运转。
  - 工具执行结果没有落成框架内的 tool message，只是拼成字符串 `prompt = f"Tool Result ..."` 继续下一轮。
  - 这会丢失 `tool_call_id`、tool name、原始结构化输出，也无法正确支持一次响应内多个 tool calls。

### 已确认的根因

- 框架内部缺少“统一消息模型”，导致模型层、qfaos 层、memory 层各自持有不同且不完整的 tool/content 表示。
- qfaos 的运行时契约仍停留在“单工具调用”设计，直接限制了上层 agent。
- memory 只保存 assistant 的 tool call，不保存 tool role 结果消息，导致多轮回填模型时信息不完整。
- 历史测试中出现过 `tool_call_id` 丢失问题，当前代码仍未从类型层根治，只是通过临时 `litellm_kwargs["messages"]` 绕过。

## Proposed Changes

### 1. 统一领域数据类型

修改文件：

- `src/domain/models.py`
- `src/domain/memory.py`
- `src/qfaos/runtime/contracts.py`
- `src/qfaos/runtime/context_facade.py`

具体改动：

- 在 `src/domain/models.py` 中新增并统一以下模型：
  - 引入 `ModelGenerationConfig`（名称可微调）承载 `temperature`、`top_p`、`max_tokens`、`output_schema`、`max_retries` 这类低频参数，并在其中提供稳定默认值。
  - `ModelRequest` 改为持有 `config: ModelGenerationConfig`，同时保留对常用字段的便捷访问属性或兼容构造方式，避免上层每次显式传一组零散参数。
  - `ModelToolCall`：框架内部的单个工具调用定义，字段至少包含 `id`、`type`、`function(name, arguments)`、`parsed_payload`（可选）和 `metadata`（可选）。
  - `ModelToolResultMessage` 或等价的 tool-role 消息字段组合：至少表达 `role="tool"`、`tool_call_id`、`name`、`content`、`structured_output`。
  - 扩展 `ModelMessage`：保留 `role/content`，新增 `tool_calls`、`tool_call_id`、`name`、`structured_content`/`metadata` 等字段，使其可统一表示 `system/user/assistant/tool` 四类消息。
  - 调整 `ModelResponse`：新增统一的 `message: ModelMessage | None` 与 `messages: tuple[ModelMessage, ...]`（若保持单条响应，可只保留 `message`），并让 `tool_calls` 成为从 `message` 派生出的兼容字段，而不是主要载体。

- 在 `src/domain/memory.py` 中把 `HotMemoryItem` 从“只适合 assistant/user 文本”升级为“可直接承载 ModelMessage 的可持久化版本”：
  - 保留 `trace_id`、`role`、`content`。
  - 增加 `tool_calls`、`tool_call_id`、`name`、`structured_output`、`metadata`。
  - 保证 `HotMemoryItem` 能无损表达 assistant tool call 消息和 tool result 消息。

- 在 `src/qfaos/runtime/contracts.py` 中收敛重复契约：
  - `QFAModelOutput` 不再重新定义一套与 `ModelResponse` 平行的模型输出字段，而是包装统一的 `ModelResponse` / `ModelMessage`，只保留 qfaos 运行时真正需要的少量便捷派生字段。
  - `QFAToolResult` 增加 `tool_call_id`、`tool_message`（或等价字段），使其能直接落 memory 并重新喂回模型。
  - `QFASessionContext.model_ask()` 的返回值设计以 `ModelResponse` 为真源，qfaos 仅做最薄封装。

- 在 `src/qfaos/runtime/context_facade.py` 中同步消费新的统一类型：
  - `_to_model_output()` 与 `_build_messages()` 直接围绕 `ModelResponse` / `ModelMessage` 工作，不再重复拼装一套松散 dict。

设计决策：

- 以 OpenAI/LiteLLM messages 为中心，不再把 tool call / tool result 当作“附属日志”。
- qfaos 对外继续暴露自己的 dataclass，但字段语义与 OpenAI/LiteLLM 对齐。
- `ModelRequest` 采用“低频参数下沉到配置对象 + 默认值内建”的方案，而不是继续把多个可选参数平铺在顶层。

### 2. 修复 model_provider 的请求/响应转换

修改文件：

- `src/model_provider/providers/litellm_adapter.py`
- `src/model_provider/validators/output_parser.py`
- `src/model_provider/routing/router.py`
- `src/model_provider/contracts.py`
- `src/model_provider/__init__.py`
- `src/domain/errors.py` 或等价的新公共错误工具文件

具体改动：

- 在 `litellm_adapter.py` 中：
  - `_to_litellm_message()` 改为根据扩展后的 `ModelMessage` 输出完整 LiteLLM/OpenAI message dict。
  - 对 `assistant` 消息：同时保留 `content` 和 `tool_calls`。
  - 对 `tool` 消息：输出 `role="tool"`、`tool_call_id`、`name`、`content`。
  - `build_model_response()` 改为先统一构造 `assistant_message`，再派生 `content` / `tool_calls` / `tool_invocations`。
  - 当 `content` 与 `tool_calls` 同时存在时仍视为成功，且在 `QFA` 层保持两者都可见。
  - 当 `tool_calls` 解析失败时，返回结构化失败信息：至少包含失败索引、tool 名称、原始 arguments、失败阶段（格式解析/Schema 校验/未授权工具）。
  - `output_schema` 存在时，只对 `content` 做 schema 解析；若同时存在 tool calls，则不因 content schema 失败而抹掉工具调用信息。
  - `function_call` 旧字段若出现，转为单元素 `tool_calls` 的兼容路径，而不是直接 `pass`。
  - 所有输入参数与中间对象尽量使用精确类型，避免把 LiteLLM 返回对象一路标成 `Any`。

- 在 `output_parser.py` 中：
  - 将 `convert_litellm_tool_calls()` 升级为返回框架内部统一 `ModelToolCall`/`CapabilityRequest` 对照结果。
  - 增加更细的异常上下文，必要时将 `ToolCallValidationError` 改为携带结构化属性。
  - 明确区分：
    - 非法 JSON arguments
    - arguments 非 object
    - tool 不在允许列表
    - payload 与 schema 不匹配
  - 保留原始输入文本，供 router 修复提示使用。

- 在 `router.py` 中：
  - `_build_repair_message()` 改为面向统一消息类型生成修复提示，不再依赖字符串拼接优先级错误的表达式。
  - 当失败来自 tool call 解析时，把失败的原始 tool call 信息写入修复提示；当失败来自 content schema 解析时，仅针对 content 修复。
  - `provider_id` 在异常路径中保证已定义，避免 `client.completion()` 前异常导致引用未初始化变量。
  - 给用户可见的错误包装统一接入公共错误格式化工具，确保错误位置与调用栈可见。

- 在新的公共错误工具文件中：
  - 新增一个面向用户展示的错误格式化工具，例如 `format_user_facing_error()` / `ErrorReportBuilder`。
  - 统一输出：错误摘要、异常类型、触发位置、精简调用栈。
  - 本轮至少接入工具调用解析失败、工具执行失败、qfaos 调用工具失败这几条链路，后续项目可复用扩展。

- 在 `contracts.py` / `__init__.py` 中：
  - 对齐新的返回类型与导出项，清理已经失效的 `parse_message_tool_calls` 导出名。

### 3. 修复 qfaos 运行时与工具执行编排

修改文件：

- `src/qfaos/runtime/context_facade.py`
- `src/qfaos/runtime/contracts.py`
- `agents/bill_management_agent.py`

具体改动：

- 在 `context_facade.py` 中：
  - `_to_model_output()` 不再取第一个 tool call，而是完整映射 `output.tool_calls`。
  - `call_pytool()` 保持单次调用单个 tool 的职责，但新增一个把 `QFAToolResult` 转成 `ModelMessage(role="tool")` / memory item 的统一辅助逻辑。
  - `add_memory()` 改为接受完整消息对象，或新增专门方法以分别记录普通消息、assistant tool call 消息、tool result 消息。
  - `_build_messages()` 改为从 runtime memory 恢复完整 `ModelMessage`，包含 `tool_call_id`、`name`、`tool_calls`。
  - `get_memory()` 返回的数据也要包含这些新字段，避免调试时丢信息。
  - 面向用户的工具调用报错使用统一错误格式化工具，至少在 `call_pytool()` 和模型调用失败回传场景接入。

- 在 `bill_management_agent.py` 中：
  - AI 主循环改成“单轮模型响应可执行多个工具”的顺序：
    1. 将用户输入写入 memory。
    2. 模型返回后，把完整 assistant message 写入 memory。
    3. 若存在多个 tool calls，按原顺序逐个执行。
    4. 每个工具结果都转成 tool-role message 写入 memory。
    5. 工具全部执行完成后，再发起下一轮模型请求，而不是把结果拼成临时字符串 prompt。
  - 当 assistant 同时输出 `content + tool_calls` 时：
    - 保留 content 到 memory。
    - 默认不立即发送给用户，继续完成工具调用链；最终是否对用户可见，交由后续模型回合决定。
  - 当工具执行失败时：
    - 也生成一条结构化的 tool result message（包含错误信息），继续回填模型，让模型有机会自修复或向用户解释。
  - 若实现过程中出现超出本计划预期的数据结构冲突或历史兼容歧义，不在代码里自行拍板，先停下并提问确认。

设计决策：

- qfaos 运行时不负责“并行执行多个工具”，先按模型给出的顺序串行执行，避免引入新的状态一致性问题。
- `bill_management_agent.py` 作为现有样例/真实入口同步改造，确保框架设计有真实消费者。

### 4. 修复 memory 持久化与回放

修改文件：

- `src/storage_memory/internal/codecs.py`
- `src/storage_memory/bootstrap.py`
- `src/storage_memory/backends/in_memory.py`
- `src/storage_memory/backends/jsonl_store.py`
- `src/orchestration_engine/context/state_context_manager.py`
- `src/domain/errors.py` 或等价的新公共错误工具文件（若 memory 层日志/错误回传需要共享）

具体改动：

- 在 `codecs.py` 中：
  - 为扩展后的 `HotMemoryItem` 实现完整序列化/反序列化。
  - assistant tool call 与 tool result message 都要可逆恢复。
  - 对历史旧格式保留兼容读取：旧记录缺少 `tool_call_id/name/structured_output` 时给默认值，不让老数据读取报错。
  - 类型反序列化只接受预期结构；遇到非预期结构直接抛出带位置与栈信息的错误，而不是继续宽松吞掉。

- 在 `bootstrap.py` 中：
  - 记录日志时增加 tool 调用相关预览字段，例如 `tool_call_count`、`tool_call_ids`、`tool_name`，方便调试。

- 在 `in_memory.py` / `jsonl_store.py` 中：
  - 不改变存储接口签名，但验证扩展字段可以无损往返。

- 在 `state_context_manager.py` 中：
  - 读取热记忆后组装 `dialogue_history` 时，不再只塞 `role/content/tool_calls`，而是按新消息模型完整恢复。

### 5. 补齐回归测试

优先修改已有测试：

- `tests/test_build_model_response.py`
  - 覆盖以下场景：
    - 纯 content
    - 单个 tool call
    - 多个 tool calls
    - content 与 tool_calls 同时存在
    - tool call arguments 非法 JSON
    - tool call payload 与 schema 不匹配
    - `ModelRequest` 使用默认生成配置与显式生成配置两种构造方式

- `tests/p05_t7/tests/custom_execute_test.py`
  - 将 stub 的 `ModelResponse` 扩为多 tool calls。
  - 断言 `session_ctx.model_ask()` 返回多工具调用结构。
  - 断言 `call_pytool()` 结果可转换为可回放的 tool message / memory item。
  - 断言 qfaos 对模型层统一请求/响应包装后，不再依赖单个 `tool_call` 字段。

- `tests/implement-p0-t2-skeleton-protocol/tests/test_storage_memory.py`
  - 增加 `HotMemoryItem` 含 assistant tool calls 与 tool result 消息的序列化/反序列化测试。

如已有测试覆盖不足，再新增根级测试文件（放在 `tests/` 下）：

- 新增一个面向完整链路的回归测试，模拟：
  - 模型首轮返回多个 tool calls；
  - qfaos 逐个执行工具；
  - memory 记录 assistant/tool 消息；
  - 下一轮请求能从 memory 构造出完整 LiteLLM 消息列表。
  - 用户可见错误文本中包含异常位置与调用栈摘要。

## Assumptions & Decisions

- 不引入“消息内容多模态 part 列表”的完整 OpenAI Responses API 兼容层；本轮只覆盖文本 `content`、assistant `tool_calls`、tool role `content` 三类必要结构。
- 不修改 `CapabilityHub`/`SchemaTranslator` 的整体架构，只让它们承载新的 dataclass 字段；若序列化验证在实现时暴露新约束，再做最小必要适配。
- 不处理真正的流式 tool call 增量输出；本轮只处理单次 completion 的完整响应对象。
- 不改现有 storage 协议函数签名，避免牵连更多层；通过扩展 `HotMemoryItem` 与 codec 达成兼容。
- 工具结果回填模型时，以结构化 tool message 为唯一真源，不再依赖 `"Tool Result (...): ..."` 这种 prompt 拼接。
- 对历史 memory 数据采取“读兼容、写新格式”策略。
- Python 代码遵循“精确类型优先”原则；除边界协议无法避免处外，不新增宽泛 `Any` 注解做兜底。<mccoremem id="01KQ4QPQWHD4DZMJTKY3KA10PS" />
- plan 与 coding 阶段若出现超预期情况，先提问再继续，不自行决定。<mccoremem id="01KQ4QPQWHD4DZMJTKY3KA10PS" />

## Verification Steps

- 静态检查：
  - 对修改过的文件运行诊断，确认没有新增类型/语法错误。

- 单元测试：
  - 运行 `tests/test_build_model_response.py`
  - 运行 `tests/p05_t7/tests/custom_execute_test.py`
  - 运行 `tests/implement-p0-t2-skeleton-protocol/tests/test_storage_memory.py`
  - 如新增链路回归测试，再一并运行该测试文件。

- 最小集成验证：
  - 构造“assistant 同时返回 content + 多个 tool_calls”的模拟响应，确认 qfaos 能顺序执行多个工具并把 tool message 写入 memory。
  - 构造“tool arguments 非法 JSON / schema 不匹配”的模拟响应，确认返回结构化错误并保留修复上下文。
  - 构造“memory 读取后再次发起模型请求”的场景，确认生成的 LiteLLM messages 含 `assistant.tool_calls` 与 `tool.tool_call_id`。

- 交付后建议：
  - 开发完成后补一次测试/审阅协作，重点复核多工具调用顺序、历史 memory 兼容和 `bill_management_agent.py` 的真实行为。
