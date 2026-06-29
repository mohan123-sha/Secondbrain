import os
import sys
import json
import httpx
from dotenv import load_dotenv

# Ensure backend imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db import get_collection

load_dotenv()

SYSTEM_PROMPT = """You are "Esperia SecondBrain", the highly sophisticated AI Organizational Memory and Meeting Intelligence Assistant for Esperia.

Your goal is to answer the user's questions utilizing ONLY the retrieved meeting transcripts and summaries provided in the context below. 

Instructions for response:
1. Ground your answers strictly in the provided meeting context. Always mention the date of the meeting when discussing decisions, statements, or updates.
2. If the context does not contain enough information to answer the question, state: "I couldn't find details on that topic in my meeting memory. Could you please specify a different question?" Do not make up facts.
3. Keep your tone professional, direct, and collaborative. Use bullet points and bold headings for readability.
4. If there is a dispute or discussion in the transcripts, explain who said what (e.g., "Mohan suggested X, whereas Shreya mentioned Y").

Retrieved Meeting Context:
========================================
{context_text}
========================================
"""

def retrieve_relevant_context(query: str, n_results: int = 5):
    """
    Search ChromaDB for the most relevant meeting chunks.
    ChromaDB handles local embedding generation automatically via LocalEmbeddingFunction.
    """
    try:
        collection = get_collection()
        if collection.count() == 0:
            print("[Search API] Warning: ChromaDB collection is empty.")
            return []
            
        print(f"[Search API] Querying ChromaDB for: '{query}'")
        results = collection.query(
            query_texts=[query],
            n_results=n_results
        )
        
        # Parse and format matching chunks
        chunks = []
        if results and "documents" in results and results["documents"]:
            docs = results["documents"][0]
            metas = results["metadatas"][0] if "metadatas" in results else []
            
            for doc, meta in zip(docs, metas):
                chunks.append({
                    "text": doc,
                    "metadata": meta
                })
        return chunks
    except Exception as e:
        print(f"[Search API] Error searching ChromaDB: {e}")
        return []


async def generate_rag_response_stream(query: str):
    """
    Retrieves context, formats prompt, queries Groq API, and yields
    response chunks for SSE (Server-Sent Events) streaming.
    """
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        yield "data: " + json.dumps({"error": "GROQ_API_KEY is missing from backend/.env."}) + "\n\n"
        return
        
    # Retrieve relevant context
    contexts = retrieve_relevant_context(query)
    
    if not contexts:
        # Yield a message stating no context is available
        response_text = "I couldn't find any relevant meeting records in my memory. Please run the ingestion pipeline first or ask about topics like onboarding, fundraising, hiring, or the product roadmap."
        yield f"data: {json.dumps({'choices': [{'delta': {'content': response_text}}]})}\n\n"
        yield "data: [DONE]\n\n"
        return
        
    # Assemble context block
    context_blocks = []
    for idx, c in enumerate(contexts):
        meta = c["metadata"]
        source = meta.get("source_file", "Unknown File")
        context_blocks.append(f"--- Context Snippet {idx+1} (Source: {source}) ---\n{c['text']}")
        
    context_text = "\n\n".join(context_blocks)
    
    # Setup messages
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(context_text=context_text)},
        {"role": "user", "content": query}
    ]
    
    # We will use Groq's high-speed Llama 3.3 70B model or Llama 3 8B
    # Groq's Llama 3.3 70B is highly capable of advanced reasoning
    groq_url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1024,
        "stream": True
    }
    
    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json"
    }
    
    print("[Search API] Initiating streaming connection with Groq API...")
    
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", groq_url, json=payload, headers=headers, timeout=60.0) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    yield f"data: {json.dumps({'error': f'Groq API error ({response.status_code}): {error_body.decode()}'})}\n\n"
                    return
                    
                async for line in response.aiter_lines():
                    if line.strip():
                        # Forward SSE events directly
                        yield f"{line}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': f'Retrieval/Groq connection failure: {str(e)}'})}\n\n"


if __name__ == "__main__":
    # Standard quick test
    print("Testing context retrieval...")
    chunks = retrieve_relevant_context("fundraising")
    for c in chunks:
        print(f"\nMatch: {c['metadata']}")
        print(c["text"][:200] + "...")
