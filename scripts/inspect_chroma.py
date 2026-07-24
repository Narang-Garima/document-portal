"""
Inspect Chroma vector database
"""
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# Load the embeddings model
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# Connect to persisted vector store
vector_store = Chroma(
    persist_directory="data/vector_store",
    embedding_function=embeddings,
    collection_name="document_portal_kb"
)

# Get collection info
collection = vector_store._collection
print(f"Total vectors: {collection.count()}")
print(f"Collection name: {collection.name}")

# Get all documents
documents = collection.get()
print(f"\nDocuments in collection: {len(documents['ids'])}")

# Show all documents with metadata
print("\n" + "="*80)
for i, (doc_id, metadata, content) in enumerate(zip(
    documents['ids'], 
    documents['metadatas'], 
    documents['documents']
)):
    print(f"\n--- Chunk {i+1} ---")
    print(f"ID: {doc_id}")
    print(f"Metadata: {metadata}")
    print(f"Content: {content}")
    print("-" * 80)
