#!/usr/bin/env python3
"""
飞书长连接手动测试辅助启动脚本

使用方法:
1. 先确保已配置飞书应用凭证:
   python -m src.app.main config-feishu --app-id <your_app_id> --app-secret <your_app_secret>

2. 运行本脚本启动长连接:
   python tests/implement-p0-t1-foundation/scripts/run_manual_test.py

3. 测试场景 (参考测试设计文档):
   - M-FS-01: 发送纯文本消息 (如 "你好") -> 期望控制台打印接收日志
   - M-FS-02: 发送富文本消息 (含链接/代码) -> 期望系统正常解析
   - M-FS-03: 发送图片消息 -> 期望控制台输出警告，不断开
   - M-FS-04: 发送语音消息 -> 期望控制台输出警告，不断开
"""

import sys
import os

# 将项目根目录加入 sys.path，以便能够正确导入 src 模块
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.app.main import main

if __name__ == "__main__":
    print("=" * 60)
    print("准备启动飞书长连接进行手动测试...")
    print("=" * 60)
    print("请在飞书客户端中找到您的机器人，并尝试发送以下内容：")
    print(" 1. 纯文本 (例如 'hello')")
    print(" 2. 包含代码块或超链接的富文本")
    print(" 3. 图片")
    print(" 4. 语音")
    print("=" * 60)
    print("如果遇到启动失败，请按照提示使用 config-feishu 命令配置您的 AppID 和 AppSecret。")
    print("=" * 60)
    print("\n[控制台日志输出如下]:")
    
    # 直接调用 main 的长连接命令
    main(["run"])
