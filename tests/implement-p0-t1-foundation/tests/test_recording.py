import pytest
import time
from unittest.mock import patch
from src.observability_hub.trace.id_generator import GlobalTraceIDGenerator, generate_trace_id
from src.observability_hub.record.recording import record, LogLevel

try:
    from pydantic import BaseModel
except ImportError:
    BaseModel = None

def test_ob_01_generate_trace_id_format():
    """测试项 OB-01: 生成追踪 ID 的基本格式"""
    trace_id = generate_trace_id()
    parts = trace_id.split("-")
    # 预期格式: prefix-timestamp-sequence-uuid (例如 trace-1600000000000-000000-abcd...)
    assert len(parts) == 4
    assert parts[0] == "trace"
    assert parts[1].isdigit()
    assert len(parts[2]) == 6 and parts[2].isdigit()
    assert len(parts[3]) == 16

def test_ob_02_multiple_trace_ids_same_millisecond():
    """测试项 OB-02: 同毫秒内生成多个追踪 ID"""
    generator = GlobalTraceIDGenerator()
    
    # 强制让 time.time() 返回相同的值，模拟同毫秒
    with patch("time.time", return_value=1600000000.123):
        trace_id_1 = generator.generate()
        trace_id_2 = generator.generate()
        
    seq_1 = int(trace_id_1.split("-")[2])
    seq_2 = int(trace_id_2.split("-")[2])
    
    assert seq_2 == seq_1 + 1

def test_ob_03_record_string_data():
    """测试项 OB-03: 记录归一化：处理字符串数据"""
    result = record(trace_id="trace_123", data="error msg", level=LogLevel.ERROR)
    
    assert result.trace_id == "trace_123"
    assert result.level == LogLevel.ERROR
    assert result.payload_type == "str"
    assert result.payload == {"message": "error msg"}
    assert isinstance(result.timestamp_ms, int)

def test_ob_04_record_nested_dict():
    """测试项 OB-04: 记录归一化：处理深层嵌套字典"""
    data = {
        "user": {
            "id": 1,
            "info": {
                "name": "test"
            }
        },
        "status": "active"
    }
    result = record(trace_id="trace_123", data=data)
    
    assert result.payload_type == "dict"
    expected_payload = {
        "user.id": 1,
        "user.info.name": "test",
        "status": "active"
    }
    assert result.payload == expected_payload

def test_ob_05_record_pydantic_model():
    """测试项 OB-05: 记录归一化：处理 Pydantic/BaseModel"""
    if BaseModel is None:
        pytest.skip("pydantic is not installed, skipping test")
        
    class MockModel(BaseModel):
        user_id: int
        role: str
        
    model_instance = MockModel(user_id=100, role="admin")
    result = record(trace_id="trace_123", data=model_instance)
    
    assert result.payload_type == "basemodel"
    assert result.payload == {"user_id": 100, "role": "admin"}

def test_ob_06_unsupported_data_type():
    """测试项 OB-06: 异常处理：不支持的数据类型"""
    with pytest.raises(TypeError, match="unsupported_record_data_type"):
        record(trace_id="trace_123", data=12345)
        
    with pytest.raises(TypeError, match="unsupported_record_data_type"):
        record(trace_id="trace_123", data=["a", "b"])