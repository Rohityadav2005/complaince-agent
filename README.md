# CTRAG Compliance Agent

An automated compliance checking agent built upon the **CTRAG** (In-Context Retrieval-based Framework for Automated Compliance Checking using LLMs) research paper. 

This agent uses:
- **Pinecone**: For Vector Database storage and dynamic retrieval (RAG).
- **Google Gemini Flash 2.5**: For LLM generation, in-context learning, and embedding creation (`text-embedding-004`).

## Setup Instructions

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables**
   - Copy `.env.example` to `.env`.
   - Add your API keys:
     - `GEMINI_API_KEY`: Get this from Google AI Studio.
     - `PINECONE_API_KEY`: Get this from your Pinecone Console.

3. **Run the Agent**
   ```bash
   python ctrag_agent.py
   ```

## How it works (CTRAG approach)
1. **Control Question Extraction:** The LLM takes raw regulatory text (e.g., GDPR snippets) and extracts actionable questions.
2. **Dynamic Evidence Retrieval:** Company documents are vectorized and stored in Pinecone. The control questions are used to search the vector DB for the most relevant evidence.
3. **In-Context Assessment:** The LLM uses the retrieved evidence as context to determine if the company is **COMPLIANT**, **NON-COMPLIANT**, or if there is a **LACK OF EVIDENCE**, providing reasoning for its decision.