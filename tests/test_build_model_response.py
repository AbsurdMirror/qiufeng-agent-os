
import sys
import os
from unittest.mock import MagicMock

# 确保可以导入项目模块
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.model_provider.providers.litellm_adapter import build_model_response
from src.domain.models import ModelRequest
from src.domain.translators.schema_translator import SchemaTranslator
from src.domain.capabilities import CapabilityRequest, CapabilityResult
from src.model_provider.routing.router import ModelRouter
import litellm
import json
from pprint import pprint

def test_build_model_response():
    # 模拟 litellm.ModelResponse
    # 注意：直接构造 litellm.ModelResponse 对象可能比较复杂，我们使用 MagicMock 模拟其结构
    mock_response = MagicMock(spec=litellm.ModelResponse)
    
    # 设置 choices
    mock_choice = MagicMock()
    mock_choice.finish_reason = 'stop'
    mock_choice.index = 0
    mock_choice.message = MagicMock()
    mock_choice.message.content = '\n\n你好！很高兴为你服务！我是你的账单管理助手，可以帮你：\n\n- 📝 **添加账单** - 记录你的每一笔收支\n- 🔍 **查询账单** - 按日期、分类、金额等条件筛选\n- ✏️ **修改账单** - 更新已有账单的信息\n- 🗑️ **删除账单** - 移除不需要的记录\n- 📊 **统计账单** - 查看收支汇总和分类统计\n\n请告诉我你需要什么帮助？'
    mock_choice.message.role = 'assistant'
    mock_choice.message.tool_calls = None
    mock_choice.message.function_call = None
    
    mock_response.choices = [mock_choice]
    
    # 设置 usage
    mock_usage = MagicMock()
    mock_usage.completion_tokens = 172
    mock_usage.prompt_tokens = 1043
    mock_usage.total_tokens = 1215
    mock_response.usage = mock_usage
    
    mock_response.model = 'MiniMax-M2.7'
    mock_response.id = '0637b187052cb10ba8ecd00c1061a59e'

    def mock_str(self, *args, **kwargs):
        return f"ModelResponse(id='{self.id}', model='{self.model}')"
    mock_response.__str__ = mock_str.__get__(mock_response, MagicMock)

    # 构造请求对象
    request = ModelRequest(
        messages=(),
        model_name='MiniMax-M2.7'
    )

    # 调用待测函数
    result = build_model_response(
        response_raw=mock_response,
        request=request,
        output_schema=None,
        fallback_model_name='fallback-model',
        provider_id='minimax'
    )

    # 1. 模拟 ModelRouter.completion 的输出模型推导过程 (T3 架构核心)
    # 在 CapabilityHub.register_instance_capabilities 时，会通过 SchemaTranslator 解析方法签名
    output_model = SchemaTranslator.func_to_output_model(ModelRouter.completion)
    print(f"\n--- Output Model Derived: {output_model.__name__} ---")

    # 2. 使用 SchemaTranslator 将 ModelResponse 实例序列化为 LLM 友好的字典 (T3 架构核心)
    # 模拟 CapabilityHub.auto_handler 中的逻辑：output = SchemaTranslator.serialize_instance(_desc.output_model, result)
    serialized_output = SchemaTranslator.serialize_instance(output_model, result)
    print("\n--- Serialized Output (dict) ---")
    pprint(serialized_output)

    # 3. 构造最终的 CapabilityResult 对象 (T3 架构核心)
    # 模拟 CapabilityHub.auto_handler 中的最终返回
    capability_result = CapabilityResult(
        capability_id="model.completion",
        success=result.success,
        output=serialized_output,
        metadata={
            "provider": result.provider_id,
            "model": result.model_name,
            "domain": "model"
        }
    )

    print("\n--- Final CapabilityResult ---")
    print(f"Capability ID: {capability_result.capability_id}")
    print(f"Success: {capability_result.success}")
    print(f"Metadata: {capability_result.metadata}")
    print("Output Data:")
    pprint(capability_result.output)

    # 验证序列化后的结构是否包含 'result' 键（SchemaTranslator 的约定）
    assert "result" in capability_result.output
    assert capability_result.output["result"]["content"] == result.content
    print("\n--- Verification Passed! ---")

if __name__ == "__main__":
    test_build_model_response()
