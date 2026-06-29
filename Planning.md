# Esperia AI Organizational Memory System

# Project Overview

This project is an AI-powered organizational memory and meeting intelligence system for Esperia.

The system ingests Zoom meeting transcripts, processes them into semantic knowledge, stores them inside a vector database, and enables AI-based conversational retrieval over historical meetings.

The architecture is designed in two phases:

1. Historical Batch Knowledge Ingestion (Current Phase)
2. Real-Time Autonomous Zoom Automation (Future Phase)

---

# Current Goal (Phase 1)

Build the complete AI memory and retrieval pipeline using already existing Zoom cloud transcripts and meeting summaries.

This phase focuses on:

* ingestion
* processing
* semantic storage
* retrieval
* AI chat over meetings

WITHOUT live Zoom webhook automation initially.

---

# Future Goal (Phase 2)

After the core memory system works successfully:

Add:

* Zoom webhook triggers
* automatic real-time ingestion
* continuous organizational learning

This converts the system into a fully autonomous AI knowledge infrastructure.

---

# Core System Vision

The system acts as:

* organizational memory
* semantic meeting archive
* AI-powered retrieval system
* knowledge assistant for Esperia

The final system should allow users to ask:

* "What did Esperia discuss about onboarding?"
* "What decisions were made regarding fundraising?"
* "Summarize the last 5 weekly meetings."
* "Who owns the hiring pipeline task?"
* "What roadmap discussions happened recently?"

---

# High-Level Architecture

## Phase 1 Architecture

```text
Historical Zoom Meeting Files
        ↓
n8n Workflow
        ↓
Python Processing Scripts
        ↓
Convert / Extract Text
        ↓
Store Files in Box (Esperia SecondBrain)
        ↓
Chunk Documents
        ↓
Generate Embeddings
        ↓
Store Semantic Memory in ChromaDB
        ↓
Retrieval Pipeline
        ↓
Groq LLM API
        ↓
AI Chat Interface
```

---

# Phase 2 Architecture

```text
Zoom Meeting Ends
        ↓
Zoom Cloud Recording + Transcript Generated
        ↓
Zoom Webhook Trigger
        ↓
n8n Workflow Triggered Automatically
        ↓
Python Processing Pipeline
        ↓
Chunk + Embed + Store
        ↓
ChromaDB Updated Automatically
        ↓
AI Knowledgebase Expands Continuously
```

---

# System Components

## 1. Zoom Cloud Recordings

Zoom cloud recordings already contain:

* transcript files
* meeting summaries
* Zoom AI summaries

These become the raw input source.

Initial ingestion uses:

* last 5 meetings
* filtered by date

---

# 2. n8n (Workflow Orchestrator)

n8n acts as the orchestration layer.

Responsibilities:

* execute workflows
* trigger Python scripts
* manage automation pipeline
* integrate APIs
* monitor execution status
* visualize workflow completion

n8n does NOT handle:

* embeddings
* vector search
* heavy AI processing

n8n is the workflow conductor.

---

# 3. Python Processing Layer

Python handles the AI-heavy processing.

Responsibilities:

* file extraction
* transcript parsing
* chunking
* embedding generation
* ChromaDB storage
* retrieval logic
* semantic search

Python scripts are executed by n8n using Execute Command nodes.

Example:

```bash
python process_meetings.py
```

---

# 4. Box Storage (Esperia SecondBrain)

Box acts as:

* centralized document storage
* organizational archive
* source-of-truth document repository

Stored files:

* transcript files
* markdown files
* summaries
* processed meeting documents

Box does NOT store vectors.

---

# 5. ChromaDB (Semantic Memory Layer)

ChromaDB stores:

* embeddings
* chunks
* semantic representations
* metadata

ChromaDB acts as the AI memory system.

Stored data:

* text chunks
* embedding vectors
* metadata
* semantic relationships

Example metadata:

```json
{
  "meeting": "Esperia Weekly Full-Team Meeting",
  "date": "2026-05-25",
  "speaker": "John"
}
```

---

# 6. Embedding Model

Initial embedding model:

```text
sentence-transformers/all-MiniLM-L6-v2
```

Reason:

* free
* lightweight
* fast
* works locally
* compatible with 8GB RAM

Embeddings convert text into semantic vectors.

Example:

```text
"Improve onboarding flow"
```

becomes:

```text
[0.182, -0.991, 0.441, ...]
```

---

# 7. Groq API (LLM Layer)

Groq API handles:

* final answer generation
* conversational responses
* summarization
* reasoning

Groq DOES NOT store memory.

ChromaDB retrieves memory.
Groq only reads retrieved context.

Architecture:

```text
User Query
    ↓
Embed Query
    ↓
Search ChromaDB
    ↓
Retrieve Relevant Chunks
    ↓
Send Chunks to Groq
    ↓
Generate Final Response
```

---

# Current Phase 1 Workflow

## Step 1 — Get Historical Meetings

Fetch:

* last 5 Zoom cloud meeting transcripts
* based on meeting dates

Input formats may include:

* TXT
* VTT
* DOCX

---

# Step 2 — Store in Esperia SecondBrain

Upload/store processed files inside:

```text
Esperia SecondBrain/
```

inside Box storage.

---

# Step 3 — Read Files

Python reads:

* transcripts
* summaries
* meeting documents

---

# Step 4 — Chunk Documents

Split meetings into semantic chunks.

Recommended:

* chunk size: 500–1000 tokens
* overlap: 100–150 tokens

---

# Step 5 — Generate Embeddings

Embedding model converts chunks into vectors.

---

# Step 6 — Store in ChromaDB

Store:

* chunks
* embeddings
* metadata

inside ChromaDB.

---

# Step 7 — Retrieval Pipeline

User asks a question.

System:

* embeds question
* searches ChromaDB
* retrieves relevant chunks
* sends chunks to Groq

Groq generates final answer.

---

# Technology Stack

## Workflow Orchestration

* n8n

## AI Processing

* Python

## Vector Database

* ChromaDB

## Embedding Model

* sentence-transformers/all-MiniLM-L6-v2

## LLM API

* Groq API

## Cloud Storage

* Box (Esperia SecondBrain)

## Transcript Source

* Zoom Cloud Recordings
* Zoom AI Meeting Summaries

---

# Design Principles

## Modular Architecture

Each component is replaceable.

Examples:

* ChromaDB → Qdrant
* Groq → OpenAI
* Box → S3
* Zoom → Google Meet

without redesigning the whole system.

---

# Phase Separation

## Phase 1

Build:

* semantic memory
* retrieval infrastructure
* AI conversational layer

## Phase 2

Add:

* Zoom webhook automation
* autonomous ingestion
* continuous memory expansion

---

# Expected MVP Outcome

The system should successfully answer:

* "What onboarding discussions happened?"
* "What did the team discuss about fundraising?"
* "Summarize the last 5 meetings."
* "What decisions were made recently?"

using real historical meeting data.

---

# Long-Term Vision

The final system evolves into:

* organizational memory engine
* AI-powered semantic archive
* company intelligence layer
* autonomous knowledge infrastructure
* conversational institutional memory system

The architecture is intentionally designed for future scalability and autonomous AI workflows.
