import os
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn
import json
import uuid

from ctrag_agent import CTRAGComplianceAgent

app = FastAPI(title="CTRAG Compliance Agent API")

# Mount the static directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Request Model
class AuditRequest(BaseModel):
    regulation_text: str

@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    pinecone_key = os.getenv("PINECONE_API_KEY")
    if not pinecone_key:
        return {"type": "error", "message": "API keys are not configured properly."}
        
    content = await file.read()
    text = ""
    
    if file.filename.lower().endswith(".pdf"):
        try:
            import PyPDF2
            import io
            reader = PyPDF2.PdfReader(io.BytesIO(content))
            for page in reader.pages:
                text += page.extract_text() + "\n"
        except Exception as e:
            return {"type": "error", "message": f"Failed to parse PDF: {str(e)}"}
    else:
        text = content.decode("utf-8", errors="ignore")
        
    if not text.strip():
        return {"type": "error", "message": "Document is empty or could not be parsed."}
        
    doc_id = str(uuid.uuid4())
    try:
        agent = CTRAGComplianceAgent(pinecone_key=pinecone_key)
        agent.ingest_document(doc_id, text, {"source": file.filename})
        return {"type": "success", "message": f"Document '{file.filename}' uploaded and indexed successfully!"}
    except Exception as e:
        return {"type": "error", "message": f"Ingestion failed: {str(e)}"}

@app.post("/api/audit/stream")
def run_audit_stream(req: AuditRequest):
    pinecone_key = os.getenv("PINECONE_API_KEY")
    
    def event_generator():
        if not pinecone_key:
            yield f"data: {json.dumps({'type': 'error', 'message': 'API keys are not configured properly.'})}\n\n"
            return
            
        try:
            agent = CTRAGComplianceAgent(pinecone_key=pinecone_key)
            for event in agent.run_full_audit_stream(req.regulation_text):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
