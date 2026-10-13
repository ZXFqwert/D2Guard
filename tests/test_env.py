import os
import sys
import time
from dotenv import load_dotenv
from openai import OpenAI

# Load .env
load_dotenv()

api_key = os.getenv("LLM_API_KEY")
base_url = os.getenv("LLM_BASE_URL")
model = os.getenv("LLM_MODEL", "deepseek-v3.2")

print(f"Testing environment configuration...")
print(f"Base URL: {base_url}")
print(f"Model: {model}")
print(f"API Key: {api_key[:6]}...{api_key[-4:] if api_key else 'None'}")

if not api_key or not base_url:
    print("ERROR: LLM_API_KEY or LLM_BASE_URL not found in .env")
    sys.exit(1)

client = OpenAI(api_key=api_key, base_url=base_url)

start_time = time.time()
try:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant for D2Guard security verification."},
            {"role": "user", "content": "Respond with 'D2Guard environment connected successfully' if you receive this."}
        ],
        max_tokens=50,
        temperature=0.0
    )
    elapsed = time.time() - start_time
    content = response.choices[0].message.content.strip()
    print(f"Latency: {elapsed:.2f}s")
    print(f"Response: {content}")
    print("SUCCESS: LLM API connection verified.")
except Exception as e:
    print(f"ERROR connecting to LLM API: {e}")
    sys.exit(1)
