from pathlib import Path
from dotenv import load_dotenv
from adaption import Adaption

load_dotenv(Path(__file__).parent / ".env")

client = Adaption()

# Select a model
model_name = "qwen3.5-397b"

# Send a request
response = client.responses.create(
    model=model_name,
    input="You are an AI research agent. Explain one potential risk of multi-agent AI systems.",
    max_output_tokens=200
)

print(f"\nModel: {model_name}")
print("\nResponse:")
print("Full response object:")
print(response)

print("\nOutput text:")
print(repr(response.output_text))