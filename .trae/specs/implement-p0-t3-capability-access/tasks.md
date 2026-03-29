# Tasks
- [x] Task 1: 建立编排层 Capability 契约
  - [x] SubTask 1.1: 定义能力描述、请求、结果与 Hub 协议
  - [x] SubTask 1.2: 将 BaseOrchestrator 与编排导出对齐到强类型 Capability 接口

- [x] Task 2: 创建 Skill Hub 最小模块与浏览器工具
  - [x] SubTask 2.1: 新建 skill_hub 模块、导出类型与初始化骨架
  - [x] SubTask 2.2: 实现最小浏览器 PyTools 能力与运行时状态探测

- [x] Task 3: 实现 Capability 转发路由
  - [x] SubTask 3.1: 建立 Skill Hub 内部的能力注册与发现机制
  - [x] SubTask 3.2: 实现模型域与工具域的统一转发入口

- [x] Task 4: 完成 LiteLLM 归一化与 MiniMax 适配
  - [x] SubTask 4.1: 新增 LiteLLM 请求/响应映射适配
  - [x] SubTask 4.2: 实现 MiniMax 客户端并保留无依赖环境下的优雅降级

- [x] Task 5: 接入应用初始化链路
  - [x] SubTask 5.1: 在 app bootstrap 中注入 Skill Hub
  - [x] SubTask 5.2: 组装可供编排层消费的 Capability Hub

- [x] Task 6: 完成最小开发自检
  - [x] SubTask 6.1: 执行语言诊断并修复编译错误
  - [x] SubTask 6.2: 执行编译级检查与主入口检查

# Task Dependencies
- Task 2 depends on Task 1
- Task 3 depends on Task 1, Task 2
- Task 4 depends on Task 1
- Task 5 depends on Task 3, Task 4
- Task 6 depends on Task 1, Task 2, Task 3, Task 4, Task 5
