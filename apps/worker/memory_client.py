"""
memory_client.py — Semantic Memory using Gemini Embeddings and Local SQLite.
Stores historical goals and decisions, and calculates similarity matches natively.
"""

import os
import json
import sqlite3
import asyncio
from typing import List, Dict, Optional
from google import genai
from config import settings


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Calculates cosine similarity between two float vectors."""
    dot_product = sum(x * y for x, y in zip(v1, v2))
    magnitude_v1 = sum(x * x for x in v1) ** 0.5
    magnitude_v2 = sum(x * x for x in v2) ** 0.5
    if not magnitude_v1 or not magnitude_v2:
        return 0.0
    return dot_product / (magnitude_v1 * magnitude_v2)


class SemanticMemoryClient:
    def __init__(self):
        self.db_path = os.path.join(os.path.dirname(__file__), "scratch", "memory.db")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._initialize_db()

    def _initialize_db(self) -> None:
        """Sets up the SQLite database and tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS codebase_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                repo_name TEXT,
                goal TEXT,
                decisions TEXT,
                embedding TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    async def get_embedding(self, text: str) -> List[float]:
        """Fetches the 768-dimension embedding vector from Gemini 3 API."""
        try:
            client = genai.Client(api_key=settings.gemini_api_key)
            # Use standard text-embedding-004 model
            resp = await client.aio.models.embed_content(
                model="text-embedding-004",
                contents=text
            )
            return resp.embeddings[0].values
        except Exception as e:
            print(f"[Memory] Failed to generate embedding: {e}")
            return []

    async def add_memory(
        self,
        task_id: str,
        repo_name: str,
        goal: str,
        decisions: str
    ) -> None:
        """Embeds and saves a completed task's decisions to persistent memory."""
        summary = f"Goal: {goal}\nDecisions & Changes: {decisions}"
        vector = await self.get_embedding(summary)
        if not vector:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO codebase_memories (task_id, repo_name, goal, decisions, embedding) VALUES (?, ?, ?, ?, ?)",
            (task_id, repo_name, goal, decisions, json.dumps(vector))
        )
        conn.commit()
        conn.close()
        print(f"[Memory] Saved semantic memory card for task {task_id}.")

    async def search_memories(self, query: str, repo_name: str, limit: int = 3) -> str:
        """
        Searches memory database using Cosine Similarity on embeddings.
        Returns a formatted block describing matches.
        """
        print(f"[Memory] Searching codebase memories for: '{query}' in {repo_name}...")
        query_vector = await self.get_embedding(query)
        if not query_vector:
            return "No historical memories retrieved."

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT task_id, goal, decisions, embedding FROM codebase_memories WHERE repo_name = ?",
            (repo_name,)
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return "No matching historical decisions found in this repository's memory."

        matches = []
        for task_id, goal, decisions, emb_str in rows:
            try:
                emb_vector = json.loads(emb_str)
                score = cosine_similarity(query_vector, emb_vector)
                matches.append({
                    "task_id": task_id,
                    "goal": goal,
                    "decisions": decisions,
                    "score": score
                })
            except Exception:
                continue

        # Sort matches by cosine similarity score descending
        matches.sort(key=lambda x: x["score"], reverse=True)
        top_matches = [m for m in matches if m["score"] > 0.65][:limit]

        if not top_matches:
            return "No semantically matching historical decisions found (score threshold < 0.65)."

        output = ["## 🧠 Relevant Historical Codebase Memories"]
        for idx, m in enumerate(top_matches, 1):
            output.append(
                f"{idx}. [Task ID: {m['task_id']}] Goal: {m['goal']} (Match Score: {m['score']:.2f})\n"
                f"   Decisions/Implementation details:\n   {m['decisions']}"
            )
        return "\n\n".join(output)
