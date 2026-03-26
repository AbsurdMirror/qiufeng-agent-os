# Tasks
- [x] Task 1: 设计并落地 P0 T1 对齐的源码目录骨架
  - [x] SubTask 1.1: 创建 src 分层目录与模块初始化文件
  - [x] SubTask 1.2: 创建应用入口与基础配置加载结构
- [x] Task 2: 实现渠道适配层 T1 能力
  - [x] SubTask 2.1: 集成 NoneBot2 应用初始化封装
  - [x] SubTask 2.2: 实现飞书 Webhook 文本接收与解析入口
- [x] Task 3: 实现编排引擎层 T1 能力
  - [x] SubTask 3.1: 定义 Agent 注册数据模型
  - [x] SubTask 3.2: 实现 Agent 注册中心接口与查询能力
- [x] Task 4: 实现监控中心 T1 能力
  - [x] SubTask 4.1: 实现全局唯一 TraceID 生成器
  - [x] SubTask 4.2: 实现归一化 record() 采集接口
- [x] Task 5: 增加验证与最小测试
  - [x] SubTask 5.1: 编写单元测试覆盖 T1 核心接口
  - [x] SubTask 5.2: 运行测试并修复问题直到通过

# Task Dependencies
- Task 2 depends on Task 1
- Task 3 depends on Task 1
- Task 4 depends on Task 1
- Task 5 depends on Task 2, Task 3, Task 4
