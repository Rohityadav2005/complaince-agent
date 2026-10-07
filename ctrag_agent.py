import os
import ollama
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

# Configuration
INDEX_NAME = "compliance-agent-docs-qwen"
EMBEDDING_MODEL = "qwen3-embedding:4b"
LLM_MODEL = "qwen3:4b"

class CTRAGComplianceAgent:
    def __init__(self, index_name=INDEX_NAME, pinecone_key=None):
        """Initializes the agent and ensures the Pinecone index exists."""
        self.pinecone_key = pinecone_key or os.getenv("PINECONE_API_KEY")
        
        if not self.pinecone_key:
            raise ValueError("No Pinecone API Key provided")
            
        self.pc = Pinecone(api_key=self.pinecone_key)
        
        self.index_name = index_name
        self._ensure_index_exists()
        self.index = self.pc.Index(index_name)

    def _ensure_index_exists(self):
        import time
        from pinecone import ServerlessSpec
        
        # Check if index exists, create if not
        if self.index_name not in self.pc.list_indexes().names():
            print(f"Creating Pinecone index: {self.index_name} (this may take a moment)...")
            
            # Detect dimension from model
            dummy_embedding = self.get_embedding("test")
            dim = len(dummy_embedding)
            print(f"Detected embedding dimension: {dim}")
            
            self.pc.create_index(
                name=self.index_name,
                dimension=dim,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1" 
                )
            )
            
            time.sleep(10)
            print("Index created successfully.")

    def get_embedding(self, text: str) -> list[float]:
        """Generates an embedding for the given text using Ollama."""
        response = ollama.embeddings(
            model=EMBEDDING_MODEL,
            prompt=text
        )
        return response['embedding']

    def ingest_document(self, doc_id: str, text: str, metadata: dict = None):
        """Ingests a company document into Pinecone as evidence."""
        print(f"Ingesting document: {doc_id}...")
        embedding = self.get_embedding(text)
        meta = metadata or {}
        meta['text'] = text 
        
        self.index.upsert(
            vectors=[{
                "id": doc_id,
                "values": embedding,
                "metadata": meta
            }]
        )

    def _generate_stream(self, prompt: str, retries: int = 10, delay: int = 2):
        import time
        for i in range(retries):
            try:
                response = ollama.chat(
                    model=LLM_MODEL,
                    messages=[{'role': 'user', 'content': prompt}],
                    stream=True
                )
                for chunk in response:
                    if 'message' in chunk and 'content' in chunk['message']:
                        yield chunk['message']['content']
                return
            except Exception as e:
                error_msg = str(e)
                wait_time = delay * (2 ** i)
                print(f"Ollama API error: {e}. Retrying in {wait_time} seconds... ({i+1}/{retries})")
                time.sleep(wait_time)
                
        raise Exception("Max retries exceeded while waiting for the Ollama API.")

    def _generate_with_retry(self, prompt: str, retries: int = 10, delay: int = 2):
        full_text = ""
        for chunk in self._generate_stream(prompt, retries, delay):
            print(chunk, end="", flush=True)
            full_text += chunk
        print() # newline after generation is done
        return full_text

    def extract_control_questions(self, regulation_text: str) -> list[str]:
        """Uses LLM to extract actionable control questions from a regulation."""
        prompt = f"""
        You are a regulatory compliance expert. 
        Given the following regulatory text, extract the key control questions that an auditor 
        needs to ask to verify if a company is compliant. 
        Return ONLY the questions, separated by newlines.
        
        Regulation:
        {regulation_text}
        """
        response = self._generate_with_retry(prompt)
        # Parse output into a list of questions
        questions = [q.strip() for q in response.strip().split('\n') if q.strip()]
        return questions

    def retrieve_evidence(self, question: str, top_k: int = 3) -> list[str]:
        """Retrieves relevant company documents for a control question using Pinecone."""
        embedding = self.get_embedding(question)
        results = self.index.query(
            vector=embedding,
            top_k=top_k,
            include_metadata=True
        )
        evidence = []
        for match in results.matches:
            if 'text' in match.metadata:
                evidence.append(match.metadata['text'])
        return evidence

    def check_compliance(self, question: str, evidence: list[str]) -> str:
        """Uses the CTRAG approach to evaluate compliance based on retrieved evidence."""
        evidence_text = "\n\n".join([f"Evidence {i+1}: {e}" for i, e in enumerate(evidence)])
        
        prompt = f"""
        You are an expert compliance auditor. 
        You will be provided with a control question derived from a regulation, and several pieces of retrieved evidence from a company's documentation.
        
        Your task is to evaluate the company's compliance status regarding the control question based STRICTLY on the provided evidence.
        
        Output one of the following statuses and provide a brief reasoning:
        1. COMPLIANT
        2. NON-COMPLIANT
        3. LACK OF EVIDENCE
        
        Control Question: {question}
        
        Evidence from Company Documents:
        {evidence_text}
        
        Output Format:
        STATUS: [Your Status]
        REASONING: [Your Reasoning]
        """
        
        response = self._generate_with_retry(prompt)
        return response

    def run_full_audit(self, regulation_text: str):
        """Runs the end-to-end CTRAG compliance checking pipeline."""
        print("\n--- Starting Full Audit ---")
        questions = self.extract_control_questions(regulation_text)
        print(f"Extracted {len(questions)} control questions.")
        
        results = {}
        for q in questions:
            print(f"\nEvaluating Question: {q}")
            evidence = self.retrieve_evidence(q)
            if not evidence:
                print("No relevant evidence found.")
            
            assessment = self.check_compliance(q, evidence)
            results[q] = assessment
            print(f"Assessment:\n{assessment}")
            
        return results

    def run_full_audit_stream(self, regulation_text: str):
        """Yields streaming events for the frontend to consume."""
        yield {"type": "status", "message": "Extracting control questions..."}
        
        prompt = f"""
        You are a compliance expert. Based on the following regulation snippet, extract a list of specific, answerable control questions that an auditor would ask to verify if a company is compliant. 
        Return ONLY the questions, one per line. No introduction or extra text.
        
        Regulation Snippet:
        {regulation_text}
        """
        
        print("\nExtracting questions...")
        full_q_text = ""
        for chunk in self._generate_stream(prompt):
            print(chunk, end="", flush=True)
            full_q_text += chunk
            yield {"type": "token", "chunk": chunk, "stage": "extraction"}
        print("\n")
            
        questions = [q.strip() for q in full_q_text.split('\n') if q.strip() and '?' in q]
        yield {"type": "questions_extracted", "questions": questions}
        
        for q in questions:
            print(f"\nEvaluating Question: {q}")
            yield {"type": "status", "message": f"Retrieving evidence for: {q}"}
            evidence = self.retrieve_evidence(q)
            
            yield {"type": "status", "message": f"Evaluating: {q}"}
            evidence_text = "\n\n".join([f"Evidence {i+1}: {e}" for i, e in enumerate(evidence)]) if evidence else "No relevant evidence found in the company documents."
            
            prompt2 = f"""
        You are a compliance auditor. Evaluate if the company complies with the control question based ONLY on the provided evidence.
        
        You must start your response with one of these EXACT statuses:
        1. STATUS: COMPLIANT
        2. STATUS: NON-COMPLIANT
        3. STATUS: LACK OF EVIDENCE
        
        Control Question: {q}
        
        Evidence from Company Documents:
        {evidence_text}
        
        Output Format:
        STATUS: [Your Status]
        REASONING: [Your Reasoning]
        """
            
            print("Evaluation:")
            full_ans = ""
            for chunk in self._generate_stream(prompt2):
                print(chunk, end="", flush=True)
                full_ans += chunk
                yield {"type": "token", "chunk": chunk, "stage": "evaluation", "question": q}
            print("\n")
                
            yield {"type": "evaluation_complete", "question": q, "full_text": full_ans}
            
        yield {"type": "done"}

# Example Usage
if __name__ == "__main__":
    # Ensure keys are set before running the agent
    pinecone_key = os.getenv("PINECONE_API_KEY")
    
    if not pinecone_key:
        print("ERROR: Please set PINECONE_API_KEY in your .env file.")
        exit(1)
        
    print("Initializing CTRAG Compliance Agent...")
    agent = CTRAGComplianceAgent(pinecone_key=pinecone_key)
    
    # 1. Ingest Example Company Document (Evidence)
    company_policy = """
    Data Protection Policy v1.2:
    All customer personal data is encrypted at rest using AES-256 encryption across all databases.
    Access to customer data is strictly limited to authorized personnel with a valid business need and requires 2FA.
    We conduct mandatory annual security and privacy training for all employees.
    """
    agent.ingest_document("doc-001", company_policy, {"source": "data_protection_policy.pdf"})
    
    # 2. Example Regulation to check against (e.g., GDPR snippet)
    gdpr_snippet = """
    Article 32 Security of processing:
    1. Taking into account the state of the art, the costs of implementation and the nature, scope, context and purposes of processing as well as the risk of varying likelihood and severity for the rights and freedoms of natural persons, the controller and the processor shall implement appropriate technical and organisational measures to ensure a level of security appropriate to the risk, including inter alia as appropriate:
    (a) the pseudonymisation and encryption of personal data;
    """
    
    # 3. Run the automated compliance audit
    agent.run_full_audit(gdpr_snippet)
