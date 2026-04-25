
import sys
import os
from unittest.mock import MagicMock
from dataclasses import dataclass

# 确保可以导入项目模块
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.model_provider.providers.litellm_adapter import build_model_response
from src.domain.models import ModelRequest
from src.domain.capabilities import CapabilityDescription
import litellm

def test_tool_call_parsing_with_objects():
    # 1. 模拟 LiteLLM 的对象结构
    @dataclass
    class MockFunction:
        name: str
        arguments: str

    @dataclass
    class MockToolCall:
        id: str
        type: str
        function: MockFunction
        
        def model_dump(self):
            return {
                "id": self.id,
                "type": self.type,
                "function": {
                    "name": self.function.name,
                    "arguments": self.function.arguments
                }
            }

    mock_response = MagicMock(spec=litellm.ModelResponse)
    
    mock_choice = MagicMock()
    mock_choice.finish_reason = 'tool_calls'
    mock_choice.message = MagicMock()
    mock_choice.message.content = '\n\n'
    
    # 模拟 tool_calls 列表，包含对象而非字典
    mock_tool_call = MockToolCall(
        id='call_123',
        type='function',
        function=MockFunction(name='tool.get_today_date', arguments='{}')
    )
    mock_choice.message.tool_calls = [mock_tool_call]
    
    mock_response.choices = [mock_choice]
    mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    mock_response.model = 'gpt-3.5-turbo'

    # 2. 构造请求
    request = ModelRequest(
        messages=(),
        model_name='gpt-3.5-turbo',
        tools=(
            CapabilityDescription(
                capability_id='tool.get_today_date',
                domain='tool',
                name='get_today_date',
                description='获取今天日期',
                input_schema={'type': 'object', 'properties': {}},
                output_schema={},
            ),
        )
    )

    # 3. 调用待测函数
    try:
        result = build_model_response(
            response_raw=mock_response,
            request=request,
            output_schema=None,
            fallback_model_name='fallback',
            provider_id='openai'
        )
        
        print(f"Success: {result.success}")
        print(f"Repair Reason: {result.repair_reason}")
        if result.success:
            print(f"Tool Calls Count: {len(result.tool_calls)}")
            if result.tool_calls:
                print(f"First Tool Call: {result.tool_calls[0].capability_id}")
        
        assert result.success is True
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].capability_id == 'tool.get_today_date'
        print("\n--- Verification Passed! ---")
        
    except Exception as e:
        print(f"\n--- Verification Failed! ---")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test_tool_call_parsing_with_objects()
