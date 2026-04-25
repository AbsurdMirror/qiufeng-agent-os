from enum import Enum


class FeishuMode(str, Enum):
    """飞书渠道运行模式"""
    long_connection = "long_connection"
    webhook = "webhook"


class ChannelType(str, Enum):
    """渠道类型枚举"""
    Feishu = "feishu"


class EventType(str, Enum):
    """事件类型枚举"""
    TextMessage = "text_message"


class ModelType(str, Enum):
    """模型类型枚举"""
    MiniMax = "minimax"


class MemoryBackend(str, Enum):
    """记忆后端类型枚举"""
    in_memory = "in_memory"
    redis = "redis"
    jsonl = "jsonl"


class SecurityPolicy(str, Enum):
    """安全原语策略决策枚举"""
    Allow = "allow"
    Deny = "deny"
    AskTicket = "ask_ticket"


class QFAEnum:
    """
    QFAOS 框架使用的所有枚举定义。
    提供层级化访问方式，同时底层基于标准 Enum 以确保 Pydantic V2 兼容性。
    """
    
    # 渠道相关
    class Channel:
        # 用于类型检查的基类或标识
        Type = ChannelType
        # 具体渠道定义
        Feishu = ChannelType.Feishu
        
        class FeishuInfo:
            Mode = FeishuMode
            
    # 为了兼容 QFAEnum.Channel.Feishu.Mode 这种写法
    # 我们需要在 Channel 类中做一些特殊处理，或者调整写法。
    # 鉴于用户之前的代码中使用了 QFAEnum.Channel.Feishu.Mode，我们尝试通过嵌套类支持。
    
    class _Channel:
        Feishu = ChannelType.Feishu
        
    class _Feishu:
        Mode = FeishuMode

    Channel = ChannelType # 这样 QFAEnum.Channel 就是一个类型了
    
    # 为了支持 QFAEnum.Channel.Feishu.Mode，我们需要让 ChannelType.Feishu 
    # 看起来像是有 Mode 属性，这很难。
    # 我们调整 QFAEnum 的组织结构，确保类型检查和访问路径都能平衡。
    
    # 重新定义 QFAEnum 以平衡 Pydantic 兼容性和访问便利性
    
    Channel = ChannelType
    Event = EventType
    Model = ModelType
    
    class Memory:
        Backend = MemoryBackend

    class Primitive:
        Policy = SecurityPolicy

    # 特殊处理飞书模式，使其路径为 QFAEnum.Feishu.Mode
    class Feishu:
        Mode = FeishuMode
