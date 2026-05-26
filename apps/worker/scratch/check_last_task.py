import sqlite3
import os

db_path = r"d:\telecode\apps\server\prisma\dev.db"

if not os.path.exists(db_path):
    print(f"Error: Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get the last task
cursor.execute("SELECT id, userId, repositoryId, mode, status, prompt, result, branchName, createdAt FROM Task ORDER BY createdAt DESC LIMIT 1")
row = cursor.fetchone()

if row:
    print("=== Last Task Details ===")
    print(f"ID: {row[0]}")
    print(f"User ID: {row[1]}")
    print(f"Repository ID: {row[2]}")
    print(f"Mode: {row[3]}")
    print(f"Status: {row[4]}")
    print(f"Prompt: {row[5]}")
    print(f"Result/Error: {row[6]}")
    print(f"Branch: {row[7]}")
    print(f"Created At: {row[8]}")
    
    # Check User Credentials
    user_id = row[1]
    cursor.execute("SELECT githubToken, geminiApiKey, githubLogin FROM User WHERE id = ?", (user_id,))
    user_row = cursor.fetchone()
    if user_row:
        github_token = user_row[0]
        gemini_key = user_row[1]
        github_login = user_row[2]
        print("\n=== User Credential Status ===")
        print(f"GitHub Login: {github_login}")
        print(f"GitHub Token: {'SET (Starts with ' + github_token[:6] + '...)' if github_token else 'NOT SET'}")
        print(f"Gemini API Key: {'SET (Starts with ' + gemini_key[:6] + '...)' if gemini_key else 'NOT SET'}")
    else:
        print("\nUser record not found in database.")
else:
    print("No tasks found in database.")

conn.close()
