# **模型抽象层 (Model Provider) 架构设计规格书**

## **第一章：模块概述与子模块组成**

模型抽象层位于 Agent-OS 的核心位置，向上为编排引擎层提供标准化的推理能力，向下屏蔽不同大模型供应商（LLM Providers）的 API 差异、协议格式及物理限制。

### **1.1 设计目标**

* **协议标准化**：实现“一次编写，到处运行”，编排层无需关注底层模型是 OpenAI、Anthropic 还是国产模型。  
* **认知高可用**：通过动态路由与自动故障切换，确保 Agent 在单一供应商宕机时仍具备推理能力。  
* **输出确定性**：引入强 Schema 校验与自愈机制，解决模型输出幻觉及格式破碎问题。  
* **资源透明化**：精准监控 Token 消耗与响应延迟，为成本控制和性能优化提供数据支撑。

### **1.2 子模块构成**

本层由以下四个功能单元组成：

1. **模型路由 (Model Routing)**：负责基于标签或名称的逻辑调度及供应商负载均衡。  
2. **模型输入转换 (Model Input Transformation)**：负责上下文物理裁剪及各家私有协议的翻译适配。  
3. **模型输出转换 (Model Output Transformation)**：负责结构化数据的强校验及模型响应的自我修复。  
4. **系统交互接口 (System Interaction)**：负责与编排层的同步响应及与监控中心的异步指标上报。

## ---

**第二章：模型路由 (Model Routing)**

本模块充当“调度中心”，决定将推理任务分配给最合适的物理模型实例。

### **2.1 路由策略**

* **显式名称匹配**：当请求指定 model\_name（如 gpt-4o）时，直接路由至对应物理端点。  
* **逻辑标签映射**：支持 model\_tag 调度。  
  * high\_reasoning \-\> 映射至深度推理模型组（如 Claude 3.5, DeepSeek V3）。  
  * fast\_speed \-\> 映射至低延迟模型组（如 GPT-4o-mini, Gemini Flash）。  
* **动态权重分配**：在同一模型组内，根据供应商的实时响应速度和可用性权重进行随机分发。

### **2.2 容灾与熔断**

* **健康检查**：实时监控各 Provider 的错误率。当连续报错超过阈值（如 3 次）时，自动将其移出可用池并进入“冷冻期”。  
* **自动 Fallback**：若主选模型请求失败（如触发 Rate Limit），路由引擎自动切换至备选组（Slave Group）进行重试。

### **2.3 技术选型**

* **LiteLLM Router**：利用其成熟的 Router 类实现基于 YAML 的模型组管理、RPM/TPM 阈值控制以及优先级调度逻辑。

## ---

**第三章：模型输入转换 (Model Input Transformation)**

本模块负责将编排层的通用请求对象转化为物理模型可理解的“方言”。

### **3.1 上下文物理控制**

* **自动裁剪 (Token Trimming)**：在调用发生前，通过 tiktoken 或相关库计算 Token。若超过目标模型 Context Window，按照“保留系统提示词，从旧到新剔除对话”的策略进行物理截断，防止 API 报错。  
* **多模态对齐**：将统一格式的图片、文件 URI 转化为对应供应商要求的 Base64 或特定云存储链接格式。

### **3.2 协议翻译器**

* **格式归一化**：利用 LiteLLM 适配层，将标准的 OpenAI Message 格式翻译为目标模型协议（如 MiniMax 的 XML 工具调用格式或 Anthropic 的特定角色定义）。  
* **参数注入**：根据路由选定的模型特性，自动调整 temperature, top\_p 等底层参数，并注入针对该模型优化的全局 Base Prompt。

### **3.3 技术选型**

* **LiteLLM Core \+ Tiktoken**：LiteLLM 负责处理异构 API 协议的序列化，Tiktoken 提供精确的输入端 Token 预计算与裁剪依据。

## ---

**第四章：模型输出转换 (Model Output Transformation)**

本模块负责对模型生成内容进行质量监控与格式对齐。

### **4.1 结构化强校验**

* **Pydantic 映射**：根据编排层定义的响应模型（Response Schema），对模型返回的字符串进行强类型校验。  
* **异常拦截**：捕捉 ValidationError 或 JSON 解析错误，拦截损坏的输出，避免干扰编排层逻辑。

### **4.2 自我修复机制 (Self-healing Loop)**

* **自愈逻辑**：当校验失败时，系统自动触发一次内部重试。  
* **报错回馈**：构造包含“错误诊断信息”的新 Prompt（例如：*“你的输出不符合 JSON Schema，错误如下：{error\_detail}，请修正后重新输出”*），要求模型重新生成。  
* **闭环阈值**：自愈重试上限默认为 1 次，若依然失败则抛出 OutputFinalError 至编排层。

### **4.3 技术选型**

* **Pydantic v2 \+ Instructor**：Pydantic 作为数据契约层确保类型安全；Instructor 框架用于驱动模型在检测到校验失败时进行自发性的 Prompt 修正与二次推理。

## ---

**第五章：系统交互接口 (System Interaction)**

本模块负责管理本层与其他架构层的通信链路。

### **5.1 编排层交互 (Orchestration Interaction)**

* **同步响应代理**：接收 Capability Proxy 的 RPC 调用，并返回标准化对象。  
* **错误协议**：定义统一的异常类（如 ProviderTimeout, FormatInvalid, InsufficientQuota），使编排层能进行针对性异常处理。

### **5.2 监控中心推送 (Observability Telemetry)**

基于 LiteLLM Callback 机制，异步上报每一笔调用的详细指标：

| 指标维度 | 关键字段 | 说明 |
| :---- | :---- | :---- |
| **成本审计** | input\_tokens, output\_tokens, cost | 实际消耗与计费 |
| **性能监控** | ttft (首字延迟), total\_latency | 响应速度评估 |
| **稳定性追踪** | retry\_count, provider\_id, finish\_reason | 链路质量回溯 |

### **5.3 技术选型**

* **LiteLLM Custom Callbacks**：利用 Python 异步钩子函数将 usage 与 latency 数据非阻塞地推送到监控总线，实现与第七层（Observability Hub）的高效对接。