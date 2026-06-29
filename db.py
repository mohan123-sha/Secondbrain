import os
import chromadb
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Global model instance for lazy loading and reuse
_embedding_model = None

def get_embedding_model():
    """Lazily load the sentence-transformer model."""
    global _embedding_model
    if _embedding_model is None:
        print("Loading local embedding model: sentence-transformers/all-MiniLM-L6-v2...")
        _embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _embedding_model

class LocalEmbeddingFunction(chromadb.EmbeddingFunction):
    """Custom embedding function to generate embeddings locally using SentenceTransformers."""
    def __call__(self, input: chromadb.Documents) -> chromadb.Embeddings:
        model = get_embedding_model()
        embeddings = model.encode(input, show_progress_bar=False)
        return embeddings.tolist()

def get_chroma_client():
    """Create a persistent ChromaDB client."""
    db_path = os.getenv("CHROMA_DB_PATH", "data/chromadb")
    # Make sure absolute path is resolved relative to the workspace directory
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    abs_db_path = os.path.abspath(os.path.join(base_dir, db_path))
    os.makedirs(abs_db_path, exist_ok=True)
    return chromadb.PersistentClient(path=abs_db_path)

def get_collection():
    """Retrieve or create the main meetings vector collection."""
    client = get_chroma_client()
    return client.get_or_create_collection(
        name="esperia_meetings",
        embedding_function=LocalEmbeddingFunction()
    )

if __name__ == "__main__":
    # Test DB connection
    print("Testing ChromaDB connection...")
    collection = get_collection()
    print(f"Connection successful! Collection '{collection.name}' has {collection.count()} items.")
