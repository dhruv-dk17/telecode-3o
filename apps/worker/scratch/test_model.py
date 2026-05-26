import asyncio
from google import genai
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

async def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("API Key not found in .env, checking settings...")
    else:
        print(f"API Key: {api_key[:10]}...")
    
    client = genai.Client(api_key=api_key)
    
    # Try calling the model
    try:
        response = await client.aio.models.generate_content(
            model="gemini-3-flash-preview",
            contents="hello",
        )
        print("Success with gemini-3-flash-preview!")
    except Exception as e:
        print(f"Failed with gemini-3-flash-preview: {e}")

    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents="hello",
        )
        print("Success with gemini-2.5-flash!")
    except Exception as e:
        print(f"Failed with gemini-2.5-flash: {e}")

asyncio.run(main())
