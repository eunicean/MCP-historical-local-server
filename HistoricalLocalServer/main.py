import anthropic
import os
from dotenv import load_dotenv, dotenv_values
load_dotenv()

myKey = os.getenv("APIKEY")
print(myKey)
client = anthropic.Anthropic(api_key=myKey)

try:
    message = client.messages.create(
        model="claude-3-haiku-20240307", # modelo de claude a usar
        max_tokens=100,
        messages=[
            {"role": "user", "content": "Hello, Claude!"}
        ]
    )
    print("API key is valid and working.")
    print(f"Claude's response: {message.content}")
except anthropic.APIError as e:
    print(f"Error testing API key: {e}")
    print("Please check your API key, billing status, or rate limits.")
