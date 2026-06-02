with open('/mnt/c/documentos/decode_asterix/native_asterix.py', 'r') as f:
    content = f.read()
with open('new_cat062.py', 'r') as f:
    new_cat062 = f.read()

start_str = "def _decode_cat062(payload: bytes, offset: int, length: int) -> List[Dict[str, Any]]:\n    \"\"\"\n    Decodifica CAT 062"
end_str = "    return records\n"

start_idx = content.find("def _decode_cat062(payload: bytes, offset: int, length: int) -> List[Dict[str, Any]]:")
if start_idx == -1:
    print("Could not find start")
    exit(1)

end_idx = content.find("def parse_payload", start_idx)
if end_idx == -1:
    print("Could not find end")
    exit(1)

old_func = content[start_idx:end_idx]

# Ensure we have correctly isolated the old function
new_content = content.replace(old_func, new_cat062)

with open('/mnt/c/documentos/decode_asterix/native_asterix.py', 'w') as f:
    f.write(new_content)

print("Patched successfully!")
