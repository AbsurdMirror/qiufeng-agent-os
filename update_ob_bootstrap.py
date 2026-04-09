with open("src/observability_hub/bootstrap.py", "r") as f:
    content = f.read()

import_text = "from src.observability_hub.request_coloring import is_request_colored"
replace_import_text = """from src.observability_hub.request_coloring import is_request_colored
from src.observability_hub.jsonl_storage import JSONLStorageEngine
from src.observability_hub.cli_logger import CLILogTailer"""

content = content.replace(import_text, replace_import_text)

init_text = """    return ObservabilityHubExports(
        layer="observability_hub",
        status="initialized",
        trace_id_generator=generate_trace_id,
        record=record,
        is_request_colored=is_request_colored,
    )"""

replace_init_text = """    return ObservabilityHubExports(
        layer="observability_hub",
        status="initialized",
        trace_id_generator=generate_trace_id,
        record=record,
        is_request_colored=is_request_colored,
        jsonl_storage=JSONLStorageEngine(),
        cli_logger=CLILogTailer(),
    )"""

content = content.replace(init_text, replace_init_text)

with open("src/observability_hub/bootstrap.py", "w") as f:
    f.write(content)
