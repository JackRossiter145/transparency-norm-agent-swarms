import os
from dotenv import load_dotenv
from adaption import Adaption

load_dotenv()

api_key = os.getenv("ADAPTION_API_KEY")

if not api_key:
    raise ValueError("API key not found. Check your .env file.")

client = Adaption(api_key=api_key)

models = client.models.list()
print(f"Connected to Adaption. Found {len(models.data)} available models.")