import json

with open(r'C:\Users\Usuario\.gemini\antigravity\brain\b02ae887-c535-42f4-b160-8feb52bdbf56\.system_generated\logs\transcript.jsonl', 'r', encoding='utf-8') as f:
    for line in reversed(f.readlines()):
        try:
            data = json.loads(line)
            if data.get('source') == 'USER_EXPLICIT' and 'PROMPT DE INGENIERÍA' in data.get('content', ''):
                with open('temp_prompt.txt', 'w', encoding='utf-8') as out:
                    out.write(data['content'])
                print("FOUND AND SAVED")
                break
        except Exception as e:
            pass
