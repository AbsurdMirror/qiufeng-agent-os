with open("src/model_provider/schema_validator.py", "r") as f:
    content = f.read()

# Fix regex escapes
content = content.replace("r'^```(?:json)?\\s*\\\\n?'", r"r'^```(?:json)?\s*\n?'")
content = content.replace("r'\\\\n?```\\s*$'", r"r'\n?```\s*$'")

with open("src/model_provider/schema_validator.py", "w") as f:
    f.write(content)
