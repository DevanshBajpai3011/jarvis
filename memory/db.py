import os
import uuid
from datetime import datetime
import chromadb
from chromadb.utils import embedding_functions


class MemoryDB:
    """
    Persistent vector database wrapper for J.A.R.V.I.S. memory using ChromaDB and SentenceTransformers.
    Supports full CRUD operations (Create, Read, Update, Delete) and semantic vector search.
    """

    def __init__(self, db_dir: str = None, collection_name: str = "jarvis_memories"):
        """
        Initializes ChromaDB persistent client and embedding function.

        Args:
            db_dir (str, optional): Path to persistent storage directory. Defaults to memory/chroma_db.
            collection_name (str): Name of vector collection (defaults to 'jarvis_memories').
        """
        if db_dir is None:
            db_dir = os.path.join(os.path.dirname(__file__), "chroma_db")

        self.db_dir = os.path.abspath(db_dir)
        os.makedirs(self.db_dir, exist_ok=True)

        self.client = chromadb.PersistentClient(path=self.db_dir)

        # Initialize SentenceTransformers embedding function
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )

        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_fn,
        )

    def add_memory(self, fact: str, category: str = "general", metadata: dict = None) -> str:
        """
        Stores a text fact/memory into the vector database with category and timestamp.

        Args:
            fact (str): Fact or text content to store.
            category (str): Category tag (default 'general').
            metadata (dict, optional): Associated key-value metadata override.

        Returns:
            str: Generated unique memory ID.
        """
        if not fact or not fact.strip():
            return ""

        fact = fact.strip()
        doc_id = str(uuid.uuid4())
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        meta = {
            "category": category or "general",
            "timestamp": now_str,
            "source": "user",
        }
        if metadata:
            meta.update(metadata)

        self.collection.add(
            documents=[fact],
            metadatas=[meta],
            ids=[doc_id],
        )

        print(f"[Memory DB] Stored memory [{doc_id[:8]}]: {fact} (Category: {category})", flush=True)
        return doc_id

    def get_all_memories(self) -> list[dict]:
        """
        Retrieves all stored memories from the persistent vector collection.

        Returns:
            list[dict]: List of memory records with ID, text, category, timestamp, and source.
        """
        try:
            records = self.collection.get()
            ids = records.get("ids", [])
            documents = records.get("documents", [])
            metadatas = records.get("metadatas", [])

            memories = []
            for i, doc_id in enumerate(ids):
                doc_text = documents[i] if i < len(documents) else ""
                meta = metadatas[i] if (metadatas and i < len(metadatas) and metadatas[i]) else {}
                memories.append({
                    "id": doc_id,
                    "text": doc_text,
                    "category": meta.get("category", "general"),
                    "timestamp": meta.get("timestamp", "N/A"),
                    "source": meta.get("source", "user"),
                })

            memories.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            return memories
        except Exception as e:
            print(f"[Memory DB Error] Failed to fetch all memories: {e}", flush=True)
            return []

    def edit_memory(self, memory_id: str, new_text: str, category: str = None) -> bool:
        """
        Updates an existing memory entry in ChromaDB.

        Args:
            memory_id (str): Unique identifier of target memory.
            new_text (str): Updated text content.
            category (str, optional): Category tag override.

        Returns:
            bool: True if successfully updated, False otherwise.
        """
        if not memory_id or not new_text or not new_text.strip():
            return False

        try:
            existing = self.collection.get(ids=[memory_id])
            metadatas = existing.get("metadatas", [{}])
            meta = metadatas[0] if (metadatas and len(metadatas) > 0 and metadatas[0]) else {}

            meta["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            if category:
                meta["category"] = category.strip()

            self.collection.update(
                ids=[memory_id],
                documents=[new_text.strip()],
                metadatas=[meta],
            )
            print(f"[Memory DB] Updated memory [{memory_id[:8]}]: {new_text.strip()}", flush=True)
            return True
        except Exception as e:
            print(f"[Memory DB Error] Failed to update memory '{memory_id}': {e}", flush=True)
            return False

    def delete_memory(self, memory_id: str) -> bool:
        """
        Deletes a memory entry from ChromaDB by ID.

        Args:
            memory_id (str): Unique memory identifier.

        Returns:
            bool: True if successfully deleted, False otherwise.
        """
        if not memory_id:
            return False

        try:
            self.collection.delete(ids=[memory_id])
            print(f"[Memory DB] Deleted memory [{memory_id[:8]}]", flush=True)
            return True
        except Exception as e:
            print(f"[Memory DB Error] Failed to delete memory '{memory_id}': {e}", flush=True)
            return False

    def query_memories(self, query: str, n_results: int = 3) -> list[str]:
        """
        Queries the vector database for memories semantically relevant to query.

        Args:
            query (str): Input query text.
            n_results (int): Number of top memories to retrieve (default 3).

        Returns:
            list[str]: Retrieved memory text strings.
        """
        if not query or not query.strip():
            return []

        total_count = self.collection.count()
        if total_count == 0:
            print(f"[Memory DB] Querying memories for: '{query.strip()}' -> Found: []", flush=True)
            return []

        actual_n = min(n_results, total_count)
        results = self.collection.query(
            query_texts=[query.strip()],
            n_results=actual_n,
        )

        documents = results.get("documents", [[]])
        retrieved_docs = documents[0] if (documents and len(documents) > 0) else []

        print(f"[Memory DB] Querying memories for: '{query.strip()}' -> Found: {retrieved_docs}", flush=True)
        return retrieved_docs


# Global default instance and module-level helper functions
_memory_db_instance = None


def get_memory_db() -> MemoryDB:
    global _memory_db_instance
    if _memory_db_instance is None:
        _memory_db_instance = MemoryDB()
    return _memory_db_instance


def add_memory(fact: str, category: str = "general", metadata: dict = None) -> str:
    return get_memory_db().add_memory(fact, category=category, metadata=metadata)


def get_all_memories() -> list[dict]:
    return get_memory_db().get_all_memories()


def edit_memory(memory_id: str, new_text: str, category: str = None) -> bool:
    return get_memory_db().edit_memory(memory_id, new_text, category)


def delete_memory(memory_id: str) -> bool:
    return get_memory_db().delete_memory(memory_id)


def query_memories(query: str, n_results: int = 3) -> list[str]:
    return get_memory_db().query_memories(query, n_results)


if __name__ == "__main__":
    db = MemoryDB()
    mem_id = db.add_memory("Sir prefers coffee with oat milk.", category="preference")
    print("All memories:", db.get_all_memories())
