import sqlite3
import json
import time
import os
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from app.config import settings
from app.utils.logger import logger

class MemoryAgent:
    def __init__(self, db_path: str = settings.SQLITE_DB_PATH, vector_db_path: str = settings.CHROMA_DB_PATH):
        self.db_path = db_path
        self.vector_db_path = vector_db_path
        self.short_term_memory: Dict[str, List[Dict[str, Any]]] = {}
        self.working_memory: Dict[str, Dict[str, Any]] = {}
        
        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(self.vector_db_path, exist_ok=True)

        # Initialize SQLite for episodic and long-term structured memory
        self._init_sqlite()
        
        # Initialize ChromaDB for semantic long-term memory
        self.chroma_client = chromadb.PersistentClient(path=self.vector_db_path)
        self.collection = self.chroma_client.get_or_create_collection(name="agent_memory")

    def _init_sqlite(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            # Episodic memory: past tasks and outcomes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS episodic_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    task_id TEXT,
                    description TEXT,
                    outcome TEXT,
                    insights TEXT,
                    timestamp REAL
                )
            """)
            # Long-term structured memory: user preferences, learned patterns
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS structured_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    key TEXT,
                    value TEXT,
                    timestamp REAL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error initializing SQLite memory: {e}")

    # --- Short-term & Working Memory ---
    async def add_short_term(self, user_id: str, item: Dict[str, Any]):
        if user_id not in self.short_term_memory:
            self.short_term_memory[user_id] = []
        self.short_term_memory[user_id].append({**item, "timestamp": time.time()})
        if len(self.short_term_memory[user_id]) > 50:
            self.short_term_memory[user_id].pop(0)

    async def update_working_memory(self, user_id: str, context: Dict[str, Any]):
        self.working_memory[user_id] = {**self.working_memory.get(user_id, {}), **context}

    async def get_working_memory(self, user_id: str) -> Dict[str, Any]:
        return self.working_memory.get(user_id, {})

    # --- Episodic Memory ---
    async def store_episodic(self, user_id: str, task_id: str, description: str, insights: str, outcome: str = "COMPLETED"):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO episodic_memory (user_id, task_id, description, outcome, insights, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, task_id, description, outcome, insights, time.time())
            )
            conn.commit()
            conn.close()
            # Also add to vector DB for semantic search
            self.collection.add(
                documents=[f"Task: {description}. Outcome: {outcome}. Insights: {insights}"],
                metadatas=[{"user_id": user_id, "type": "episodic", "task_id": task_id}],
                ids=[f"episodic_{task_id}_{int(time.time())}"]
            )
        except Exception as e:
            logger.error(f"Error storing episodic memory: {e}")

    # --- Semantic Long-term Memory (Vector) ---
    async def store_semantic(self, user_id: str, text: str, metadata: Dict[str, Any] = None):
        try:
            self.collection.add(
                documents=[text],
                metadatas=[{**(metadata or {}), "user_id": user_id, "type": "semantic"}],
                ids=[f"semantic_{user_id}_{int(time.time() * 1000)}"]
            )
        except Exception as e:
            logger.error(f"Error storing semantic memory: {e}")

    async def retrieve_context(self, user_id: str, query: str, n_results: int = 5) -> Dict[str, Any]:
        """
        Retrieve relevant context from semantic memory.
        """
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where={"user_id": user_id}
            )
            documents = results["documents"][0] if results["documents"] else []
            return {"relevant_past_experiences": documents}
        except Exception as e:
            logger.error(f"Error retrieving semantic memory: {e}")
            return {}

    # --- Summarization & Compression ---
    async def summarize_context(self, user_id: str) -> str:
        items = self.short_term_memory.get(user_id, [])
        if not items: return ""
        summary = f"Summary of last {len(items)} interactions: " + "; ".join([str(i.get("content", "")) for i in items[-5:]])
        return summary

memory_agent = MemoryAgent()
