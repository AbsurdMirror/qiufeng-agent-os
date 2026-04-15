import pytest
from src.orchestration_engine.runtime.langgraph_runtime import LangGraphRuntime, LangGraphExecutable
from src.observability_hub.coloring.request_coloring import is_request_colored, create_coloring_state

def test_oe_06_compile_valid_entrypoint():
    """测试项 OE-06: 编译有效的入口点"""
    runtime = LangGraphRuntime()
    executable = runtime.compile_entrypoint("src.workflows:graph")
    
    assert isinstance(executable, LangGraphExecutable)
    assert executable.entrypoint == "src.workflows:graph"
    # P0 T2 阶段占位，所以是 None
    assert executable.compiled_graph is None

def test_oe_07_compile_invalid_entrypoint():
    """测试项 OE-07: 编译无效（空）入口点"""
    runtime = LangGraphRuntime()
    
    with pytest.raises(ValueError, match="invalid_langgraph_entrypoint"):
        runtime.compile_entrypoint("")
        
    with pytest.raises(ValueError, match="invalid_langgraph_entrypoint"):
        runtime.compile_entrypoint("   ")

def test_ob_07_colored_request_test():
    """测试项 OB-07: 染色请求判定（基于 context debug 字段）"""
    context = {"trace_id": "t-1", "is_debug": True}
    assert is_request_colored(context) is True
    
    context2 = {"trace_id": "t-2", "debug": "true"}
    assert is_request_colored(context2) is True

def test_ob_08_colored_request_debug():
    """测试项 OB-08: 染色请求判定（基于 state trace_id 匹配）"""
    state = create_coloring_state(trace_ids={"trace-debug-456"})
    context = {"trace_id": "trace-debug-456"}
    assert is_request_colored(context, state) is True

def test_ob_09_normal_request():
    """测试项 OB-09: 普通请求判定"""
    state = create_coloring_state(trace_ids={"trace-debug-456"})
    context = {"trace_id": "trace-170000000-001"}
    assert is_request_colored(context, state) is False
    assert is_request_colored({"trace_id": "normal"}) is False
