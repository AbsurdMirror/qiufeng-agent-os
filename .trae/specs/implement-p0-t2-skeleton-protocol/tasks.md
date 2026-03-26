# Tasks
- [x] Task 1: 完成渠道层 UniversalEvent 协议与飞书映射
  - [x] SubTask 1.1: 新增通用 UniversalEvent 领域模型并补齐字段契约
  - [x] SubTask 1.2: 将飞书长连接/Webhook 解析统一映射到 UniversalEvent

- [x] Task 2: 完成编排层执行骨架（OE-P0-02/OE-P0-03）
  - [x] SubTask 2.1: 新增 BaseOrchestrator 抽象基类与 RuntimeContext 类型
  - [x] SubTask 2.2: 新增 LangGraph 运行时骨架加载器与编译入口占位

- [x] Task 3: 重建模型抽象层最小接口适配（MP-P0-08）
  - [x] SubTask 3.1: 新建 model_provider 模块导出与初始化骨架
  - [x] SubTask 3.2: 定义统一模型请求/响应结构与同步调用接口

- [x] Task 4: 重建存储与记忆层热记忆与协议（SM-P0-01/SM-P0-05）
  - [x] SubTask 4.1: 新建 storage_memory 模块导出与初始化骨架
  - [x] SubTask 4.2: 定义热记忆载体接口与标准存取协议，提供内存回退实现

- [x] Task 5: 实现监控中心请求染色并接入应用（OB-P0-02）
  - [x] SubTask 5.1: 新增请求染色判定逻辑与导出类型
  - [x] SubTask 5.2: 在 app bootstrap 中接入模型层与存储层初始化，并对齐类型

- [x] Task 6: 完成最小开发自检（不含测试）
  - [x] SubTask 6.1: 执行语言诊断并修复语法/类型错误
  - [x] SubTask 6.2: 执行编译级检查并确认命令入口不回退

# Task Dependencies
- Task 2 depends on Task 1
- Task 3 depends on Task 2
- Task 4 depends on Task 2
- Task 5 depends on Task 3, Task 4
- Task 6 depends on Task 1, Task 2, Task 3, Task 4, Task 5
