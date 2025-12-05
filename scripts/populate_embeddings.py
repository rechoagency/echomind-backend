"""
One-time script to populate document_embeddings from document_chunks.
Run this via the deployed backend or locally with proper env vars.

This script:
1. Reads chunks from document_chunks for a client
2. Generates OpenAI embeddings
3. Inserts into document_embeddings (which RAG queries)
"""

import os
import sys
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from supabase_client import get_supabase_client
from openai import OpenAI


def populate_embeddings(client_id: str):
    """Populate document_embeddings from document_chunks for a client."""

    supabase = get_supabase_client()
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    print(f"🔄 Populating embeddings for client: {client_id}")

    # Get chunks from document_chunks
    chunks = supabase.table("document_chunks")\
        .select("id, document_id, chunk_text, chunk_index, client_id")\
        .eq("client_id", client_id)\
        .order("chunk_index")\
        .execute()

    if not chunks.data:
        print("❌ No chunks found in document_chunks")
        return {"success": False, "error": "No chunks found"}

    print(f"📄 Found {len(chunks.data)} chunks")

    # Get document filenames for metadata
    doc_ids = list(set(c["document_id"] for c in chunks.data))
    docs = supabase.table("document_uploads")\
        .select("id, filename")\
        .in_("id", doc_ids)\
        .execute()

    doc_filenames = {d["id"]: d["filename"] for d in (docs.data or [])}

    embeddings_created = 0
    errors = []

    for chunk in chunks.data:
        chunk_id = chunk["id"]
        document_id = chunk["document_id"]
        chunk_text = chunk["chunk_text"]
        chunk_index = chunk["chunk_index"]
        filename = doc_filenames.get(document_id, "unknown")

        # Check if embedding already exists
        existing = supabase.table("document_embeddings")\
            .select("id")\
            .eq("document_id", document_id)\
            .eq("chunk_index", chunk_index)\
            .execute()

        if existing.data:
            print(f"  ⏭️  Chunk {chunk_index} already has embedding")
            continue

        # Generate embedding
        try:
            print(f"  🧠 Generating embedding for chunk {chunk_index} ({len(chunk_text)} chars)...")
            response = openai_client.embeddings.create(
                model="text-embedding-ada-002",
                input=chunk_text[:8000]
            )
            embedding = response.data[0].embedding

            # Insert into document_embeddings
            embedding_record = {
                "document_id": document_id,
                "client_id": client_id,
                "chunk_text": chunk_text,
                "chunk_index": chunk_index,
                "embedding": embedding,
                "metadata": {
                    "filename": filename,
                    "char_count": len(chunk_text),
                    "source": "populate_embeddings_script"
                },
                "created_at": datetime.utcnow().isoformat()
            }

            supabase.table("document_embeddings").insert(embedding_record).execute()
            embeddings_created += 1
            print(f"  ✅ Inserted embedding for chunk {chunk_index}")

        except Exception as e:
            error_msg = f"Chunk {chunk_index}: {str(e)}"
            errors.append(error_msg)
            print(f"  ❌ Error: {error_msg}")

    print(f"\n{'='*50}")
    print(f"✅ Created {embeddings_created} embeddings")
    if errors:
        print(f"❌ {len(errors)} errors occurred")

    return {
        "success": True,
        "embeddings_created": embeddings_created,
        "errors": errors
    }


if __name__ == "__main__":
    # Touchstone client ID
    TOUCHSTONE_ID = "999ac53f-0217-4234-b522-9bdfe9ff3bfd"

    result = populate_embeddings(TOUCHSTONE_ID)
    print(f"\nResult: {result}")
