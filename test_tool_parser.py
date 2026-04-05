from src.skill_hub.tool_parser import parse_doxygen_to_json_schema

def example_tool(query: str, limit: int = 10, include_images: bool = False) -> list:
    """
    Search the web for a given query.

    This tool uses a web crawler to find results.

    @param str query The search query string
    @param int limit The maximum number of results to return
    @param bool include_images Whether to include images in the results
    @return A list of search results
    """
    pass

schema = parse_doxygen_to_json_schema(example_tool)
print(schema)
assert schema["type"] == "object"
assert "query" in schema["properties"]
assert schema["properties"]["query"]["type"] == "string"
assert schema["properties"]["limit"]["type"] == "integer"
assert schema["properties"]["include_images"]["type"] == "boolean"
assert schema["required"] == ["query"]

print("Tool parser tests passed!")
