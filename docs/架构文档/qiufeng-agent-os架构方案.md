<!-----



Conversion time: 2.336 seconds.


Using this Markdown file:

1. Paste this output into your source file.
2. See the notes and action items below regarding this conversion run.
3. Check the rendered output (headings, lists, code blocks, tables) for proper
   formatting and use a linkchecker before you publish this page.

Conversion notes:

* Docs™ to Markdown version 2.0β2
* Mon Mar 23 2026 23:13:27 GMT-0700 (北美太平洋夏令时间)
* Source doc: Agent-OS 架构方案
----->



## 第一章：架构概述

Agent-OS 采用分层解耦的设计理念，确保系统在集成复杂工具（如浏览器自动化）和多端接入（如飞书、微信）时保持稳定。


### 5+1 核心模块概览



1. **渠道适配层 (Channel Gateway)** 🔌：负责屏蔽不同通讯平台的差异。
2. **编排引擎层 (Orchestration Engine)** 🧠：系统大脑，负责任务拆解与状态流转。
3. **模型抽象层 (Model Provider)** 💡：统一的大模型调用接口。
4. **技能与工具层 (Skill Hub)** 🛠️：执行单元，包含 MCP 协议和浏览器操作。
5. **存储与记忆层 (Memory & Persistence)** 💾：负责长短期记忆与数据持久化。
6. **全栈监控与治理中心 (Observability Hub)** 📊：底座模块，提供链路追踪与成本控制。


## 

---
第二章：渠道适配层 (Channel Gateway)

本层是系统与外界沟通的桥梁。



* **核心功能**：将来自 Telegram、飞书、微信等渠道的原始消息转换为统一的 UniversalEvent 格式，并处理多模态输入。
* **技术栈**：基于 **NoneBot2** 框架，利用其插件系统适配不同的 Bot 协议（OneBot, Telegram API 等），飞书侧采用长连接（WebSocket）接入。
* **交互方式**：接收用户输入后，将格式化的上下文推送到编排引擎；执行完毕后，根据原始渠道类型回传渲染后的消息卡片。


## 

---
第三章：编排引擎层 (Orchestration Engine)

这是平台最复杂的逻辑核心，负责“如何思考”。



* **核心功能**：管理任务状态机。例如，在“炒股 Agent”中，它控制从“获取股价”到“搜索新闻”再到“得出结论”的逻辑跳转。
* **技术栈**：使用 **LangGraph**。它支持循环图结构，非常适合需要“自我反思”和“多轮纠错”的复杂场景。
* **交互方式**：从模型层获取决策建议，指令工具层执行具体动作，并将过程状态存入存储层。


## 

---
第四章：模型抽象层 (Model Provider)

屏蔽底层 LLM 供应商的差异化，提供稳定的推理能力。



* **核心功能**：统一 Prompt 模板管理，实现模型负载均衡与故障切换（如 GPT-4o 宕机时自动切换至 Claude 3.5）。
* **技术栈**：集成 **LiteLLM** 或 **OpenRouter**。
* **交互方式**：接收编排引擎的推理请求，返回结构化的 JSON 数据，确保输出符合预定义的 Schema。


## 

---
第五章：技能与工具层 (Skill Hub)

这是 Agent 的“手脚”，负责改变现实世界或获取实时信息。



* **核心功能**：集成 **MCP (Model Context Protocol)** 协议工具（如金融 API）和 **Browser-use**（自动化浏览器）。
* **技术栈**：mcp-python-sdk 用于标准化 API 接入，Playwright 驱动浏览器模拟真实用户登录各家 AI 网页版。
* **交互方式**：被动接受编排引擎的指令，执行后返回原始观测数据（Observation）。


## 

---
第六章：存储与记忆层 (Memory & Persistence)

为 Agent 提供跨会话的记忆能力。



* **核心功能**：存储用户偏好、会话历史、向量化知识库以及 Agent 运行的 Checkpoints。
* **技术栈**：**PostgreSQL + pgvector**（关系型数据与向量合一），**Redis**（用于高频的状态读写）。
* **交互方式**：为编排引擎提供上下文检索支持，确保 Agent “记得”用户之前的操作。


## 

---
第七章：全栈监控与治理中心 (Observability Hub)

这是平台的兜底模块，解决“Agent 为什么跑偏了”的问题。



* **核心功能**：
    * **链路追踪**：可视化查看每一次 Token 消耗和工具调用的耗时。
    * **调试回放**：记录失败任务的状态，允许开发者在沙盒中重放。
* **技术栈**：**LangSmith**（专业 Agent 追踪）+ **OpenTelemetry**（通用指标）。
* **交互方式**：以旁路监控的形式采集所有模块的日志和指标，不干扰主业务流。
