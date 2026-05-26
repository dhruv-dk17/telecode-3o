import sqlite3
import os
import asyncio
from google import genai

db_path = r"d:\telecode\apps\server\prisma\dev.db"

if not os.path.exists(db_path):
    print(f"Error: Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get last user credentials
cursor.execute("SELECT id, geminiApiKey FROM User ORDER BY createdAt DESC LIMIT 1")
row = cursor.fetchone()
conn.close()

if not row:
    print("No users found.")
    exit(1)

user_id, api_key = row
print(f"Testing Gemini Key for User {user_id}...")
print(f"Key starts with: {api_key[:8]}... Length: {len(api_key)}")

async def test_call():
    try:
        client = genai.Client(api_key=api_key)
        print("SDK client initialized successfully. Making API call...")
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",  # Using standard public model
            contents="Say 'API Key Works!'"
        )
        print(f"SUCCESS! Response: {response.text}")
    except Exception as e:
        print("\n❌ Gemini API Call Failed!")
        import traceback
        traceback.print_exc()

asyncio.run(test_call())
