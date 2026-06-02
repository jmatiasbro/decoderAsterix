import os

transcript_path = r"C:\Users\Usuario\.gemini\antigravity\brain\b02ae887-c535-42f4-b160-8feb52bdbf56\.system_generated\logs\transcript.jsonl"

if not os.path.exists(transcript_path):
    print("Transcript not found")
else:
    print("Transcript found! Searching...")
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for i, line in enumerate(f):
            if "7005" in line or "2473" in line:
                print(f"Line {i}: {line[:150]}...")
