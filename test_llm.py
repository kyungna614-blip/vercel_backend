"""
Quick test: verify the Anthropic API key works by sending a minimal request.
Run: python test_llm.py
"""
import os
import sys

# Load .env
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

api_key = os.getenv("ANTHROPIC_API_KEY", "")

if not api_key:
    print("FAIL: ANTHROPIC_API_KEY is empty or not set in .env")
    sys.exit(1)

# Mask the key for display
masked = api_key[:10] + "..." + api_key[-4:]
print(f"Key found: {masked}")
print("Testing API call to Claude...")

import anthropic

# List of models to try (newest to oldest)
MODELS_TO_TRY = [
    "claude-sonnet-4-20250514",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-haiku-20240307",
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
]

try:
    client = anthropic.Anthropic(api_key=api_key)
    
    # First, test auth by listing models or just trying calls
    success = False
    for model_name in MODELS_TO_TRY:
        try:
            print(f"  Trying model: {model_name} ... ", end="")
            message = client.messages.create(
                model=model_name,
                max_tokens=50,
                messages=[
                    {"role": "user", "content": "Say 'API key is working!' and nothing else."}
                ]
            )
            response_text = message.content[0].text
            print("SUCCESS!")
            print(f"\n{'='*50}")
            print(f"  Model:    {message.model}")
            print(f"  Response: {response_text}")
            print(f"  Tokens:   {message.usage.input_tokens} in / {message.usage.output_tokens} out")
            print(f"{'='*50}")
            print(f"\nSUCCESS: Anthropic API key is valid and working!")
            success = True
            break
        except anthropic.NotFoundError:
            print("not available")
            continue
        except anthropic.AuthenticationError:
            print("AUTH FAILED")
            print("\nFAIL: API key is INVALID (authentication rejected)")
            sys.exit(1)
        except anthropic.PermissionError as e:
            print(f"no permission: {e}")
            continue
    
    if not success:
        print("\nWARNING: Key authenticated but no models are accessible.")
        print("This could mean:")
        print("  - The API key has restricted model access")
        print("  - Your account/plan doesn't include these models")
        print("  - The key is workspace-scoped with limited permissions")
        sys.exit(1)

except anthropic.AuthenticationError:
    print("\nFAIL: API key is INVALID (authentication error)")
    sys.exit(1)
except anthropic.RateLimitError:
    print("\nWARNING: Rate limited — but key IS valid (just throttled)")
except Exception as e:
    print(f"\nERROR: {type(e).__name__}: {e}")
    sys.exit(1)
