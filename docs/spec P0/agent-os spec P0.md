### **第一章：系统运行的最小支持 —— 总体规格概览**

本章节从系统全局视角描述各层级在 P0 阶段为了实现系统基础运行必须达到的状态。

| specId | 层级名称 | P0 总体规格描述 |
| :---- | :---- | :---- |
| SYS-P0-01 | **渠道适配层 (Channel Gateway)** | 集成 **NoneBot2**，实现协议适配驱动、事件归一化引擎、响应分发渲染器、会话上下文控制器的基础功能，接入飞书长连接渠道。 |
| SYS-P0-02 | **编排引擎层 (Orchestration Engine)** | 集成 **LangGraph**，实现执行驱动器、状态与运行时上下文管理器的基础功能，支持有状态图逻辑驱动与节点间的 RuntimeContext 数据传递。 |
| SYS-P0-03 | **技能与工具层 (Skill Hub)** | 实现 **PyTools 模块**与系统交互模块的基础功能，为 pytools 开发基于 **Playwright** 的浏览器工具。 |
| SYS-P0-04 | **模型抽象层 (Model Provider)** | 集成 **LiteLLM** 与 **Pydantic**，实现模型路由、模型输入转换、模型输出转换的基础功能，跑通 **MiniMax** 模型。 |
| SYS-P0-05 | **存储与记忆层 (Storage & Memory)** | 实现分级上下文管理器的**热记忆**功能，实现系统交互网关的基础功能。 |
| SYS-P0-06 | **全栈监控与治理中心 (Observability Hub)** | 集成 **JSONL**，实现混合存储模块的**调试引擎**功能，实现系统交互引擎的基础功能。 |

### ---

**第二章：渠道适配层 (Channel Gateway) P0 规格详述**

| specId | 对应子模块 | spec 描述 |
| :---- | :---- | :---- |
| GW-P0-01 | 协议适配驱动 (Protocol Adapter) | **框架集成**：集成 NoneBot2 基础框架。 |
| GW-P0-02 | 协议适配驱动 (Protocol Adapter) | **链路调通**：调通飞书长连接（WebSocket）并实现文本提问接收。 |
| GW-P0-03 | 事件归一化引擎 (Normalization Engine) | **结构定义**：定义系统通用 UniversalEvent 数据结构。 |
| GW-P0-04 | 事件归一化引擎 (Normalization Engine) | **消息转换**：实现飞书原始消息向通用结构的映射转化。 |
| GW-P0-05 | 会话上下文控制器 (Session Context) | **身份映射**：实现 open\_id 到系统逻辑 UUID 的转换。 |
| GW-P0-06 | 会话上下文控制器 (Session Context) | **消息去重**：实现基于指纹的消息去重与幂等机制。 |
| GW-P0-07 | 响应分发渲染器 (Response Renderer) | **响应原语**：定义 ReplyText 纯文本响应标准。 |
| GW-P0-08 | 响应分发渲染器 (Response Renderer) | **异步接口**：实现可被随时调用的异步消息回传接口。 |
| GW-P0-09 | 响应分发渲染器 (Response Renderer) | **渠道适配**：实现飞书渠道的原语转换与最终消息投递。 |

### ---

**第三章：编排引擎层 (Orchestration Engine) P0 规格详述**

| specId | 对应子模块 | spec 描述 |
| :---- | :---- | :---- |
| OE-P0-01 | Agent 注册中心 (Agent Registry) | **注册接口**：定义支持元数据与身份声明的 Agent 注册接口。 |
| OE-P0-02 | 执行驱动器 (Execution Runtime) | **基类定义**：定义 BaseOrchestrator 抽象基类以规范执行接口。 |
| OE-P0-03 | 执行驱动器 (Execution Runtime) | **引擎集成**：集成 LangGraph 核心并支持有状态图的构建编译。 |
| OE-P0-04 | 状态与运行时上下文管理器 | **记忆读取**：实现历史记忆的拉取、解析与状态转换。 |
| OE-P0-05 | 状态与运行时上下文管理器 | **上下文维护**：实现运行时 RuntimeContext 的动态更新与同步。 |
| OE-P0-06 | 状态与运行时上下文管理器 | **状态持久化**：实现执行上下文向存储与记忆层的异步持久化。 |
| OE-P0-07 | 能力注入代理 (Capability Proxy) | **契约定义**：定义 Capability 接口的获取、调用与返回协议。 |

### ---

**第四章：技能与工具层 (Skill Hub) P0 规格详述**

| specId | 对应子模块 | spec 描述 |
| :---- | :---- | :---- |
| SH-P0-01 | PyTools 模块 (PyTools Module) | **安全原语实现**：定义并实现 PyTools 的安全原语接口，限制工具的资源访问与库调用权限。 |
| SH-P0-02 | PyTools 模块 (PyTools Module) | **工具规范解析**：基于 Python Doxygen 注释，自动生成符合 LLM 规范的 Tool Spec（JSON Schema）。 |
| SH-P0-03 | PyTools 模块 (PyTools Module) | **浏览器工具开发**：基于 **browser-use** 开发浏览器原子工具，支持多平台 AI 网页版交互。 |
| SH-P0-04 | 系统交互模块 (System Interaction) | **转发路由实现**：基于 Capability 接口实现编排层到 PyTools 内部函数的动态转发路由。 |

### ---

**第五章：模型抽象层 (Model Provider) P0 规格详述**

| specId | 对应子模块 | spec 描述 |
| :---- | :---- | :---- |
| MP-P0-01 | 模型路由 (Model Routing) | **显式名称匹配**：实现基于物理名称（Model Name）的直接调度匹配机制。 |
| MP-P0-02 | 模型输入转换 (Input Trans) | **自动裁剪**：集成 **Tiktoken**，实现基于模型上下文窗口的输入文本物理裁剪。 |
| MP-P0-03 | 模型输入转换 (Input Trans) | **格式归一化**：集成 **LiteLLM**，实现不同供应商 API 协议向统一 Message 格式的转换。 |
| MP-P0-04 | 模型输入转换 (Input Trans) | **MiniMax 适配**：完成 MiniMax 模型的驱动适配，确保模型调用通路完全调通。 |
| MP-P0-05 | 模型输出转换 (Output Trans) | **定义输出与提示词**：规范化模型输出结构（Response Schema）与系统级提示词模板。 |
| MP-P0-06 | 模型输出转换 (Output Trans) | **结构化强校验**：集成 **Pydantic**，根据定义的 Schema 对模型返回内容进行强制类型与格式验证。 |
| MP-P0-07 | 模型输出转换 (Output Trans) | **基础自愈机制**：实现简单的自愈逻辑，在校验失败时尝试自动修复或重试。 |
| MP-P0-08 | 系统交互接口 (System Interaction) | **接口适配**：实现并适配与编排引擎层（Orchestration Engine）之间的同步交互接口。 |

### ---

**第六章：存储与记忆层 (Storage & Memory) P0 规格详述**

| specId | 对应子模块 | spec 描述 |
| :---- | :---- | :---- |
| SM-P0-01 | 分级上下文管理器 (Context Tiering) | **热记忆载体**：集成 **Redis** 实现热记忆（Hot Memory）的物理存储。 |
| SM-P0-02 | 分级上下文管理器 (Context Tiering) | **热记忆策略**：实现基于 LIFO 逻辑的最近 N 轮对话原文缓存与自动淘汰策略。 |
| SM-P0-03 | 全量历史数据库 (Full History DB) | **持久化存储**：实现对话报文与最终调研报告的无损持久化存入逻辑。 |
| SM-P0-04 | 系统交互网关 (System Interaction Gateway) | **上下文注入**：提供被动注入接口，供编排引擎初始化节点状态时拉取历史摘要。 |
| SM-P0-05 | 系统交互网关 (System Interaction Gateway) | **存取协议实现**：定义并实现标准的数据存取协议，适配编排引擎的运行时持久化需求。 |

### ---

**第七章：全栈监控与治理中心 (Observability Hub) P0 规格详述**

| specId | 对应子模块 | spec 描述 |
| :---- | :---- | :---- |
| OB-P0-01 | 系统交互引擎 (System Interaction Engine) | **TraceID 生成**：实现全局唯一的 trace\_id 生成机制，标记单次请求的全生命周期。 |
| OB-P0-02 | 系统交互引擎 (System Interaction Engine) | **请求染色机制**：实现染色标记（Request Coloring）判定逻辑，决定是否开启全量日志采集。 |
| OB-P0-03 | 系统交互引擎 (System Interaction Engine) | **归一化采集接口**：提供统一的 record() 接口，屏蔽底层存储差异，接收各层级的监控数据。 |
| OB-P0-04 | 混合存储模块 (Hybrid Storage Module) | **调试引擎实现**：集成 **JSONL** 格式，实现大载荷调试数据（Raw Prompt, Tool Observation）的物理存储。 |
| OB-P0-05 | 混合存储模块 (Hybrid Storage Module) | **滚动清理策略**：实现基于容量或时间的日志滚动机制，防止 JSONL 文件无限增长。 |
| OB-P0-06 | 开发交互中心 (Developer Interaction Center) | **CLI 实时日志**：提供基于命令行（CLI）的实时结构化日志输出，支持按 TraceID 过滤调试信息。 |
