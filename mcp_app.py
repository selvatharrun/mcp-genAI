# mcp_app.py
import base64
import logging
import os
from typing import Optional

from fastapi import FastAPI, Request
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

# ---- Logging ----
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("mcp_app")

# ---- Try optional imports ----
try:
    from fastmcp import FastMCP
except Exception as e:
    FastMCP = None
    logger.warning("fastmcp import failed: %s", e)

try:
    from google.cloud import storage
except Exception as e:
    storage = None
    logger.warning("google.cloud.storage import failed: %s", e)

try:
    from Class.chat import automated_chat
except Exception:
    logger.warning("automated_chat import failed, using stub")

    def automated_chat(question: str, file_path: str = None, stream_response: bool = False, chat_history=None):
        return {"stub": True, "question": question, "file_path": file_path}

try:
    from Class.OCR import process_pdf_with_document_ai
except Exception:
    logger.warning("OCR import failed, using stub")

    def process_pdf_with_document_ai(gcs_uri: str):
        return {"success": False, "error": "OCR module not available", "full_text": "", "pages": [], "form_fields": [], "confidence_score": None}

try:
    from Class.Precedent import find_precedents
except Exception:
    logger.warning("Precedent import failed, using stub")

    def find_precedents(user_clause: str, location: str = "US") -> str:
        return "Precedent module not available. Please check the Precedent.py file and dependencies."

# ---- MCP Setup ----
MCP_NAME = os.getenv("MCP_NAME", "LegalDemystifierMCP")
mcp = FastMCP(MCP_NAME) if FastMCP else None
mcp_asgi = mcp.http_app(path="/", transport="streamable-http") if mcp else None

# ---- Parent FastAPI app ----
app = FastAPI(
    title="LegalDemystifier Backend",
    lifespan=mcp_asgi.lifespan if mcp_asgi else None,
)

# ---- CORS ----
allowed_origins = [
    os.getenv("FRONTEND_ORIGIN", "http://localhost:3000"),
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "mcp-session-id", "MCP-Session-Id", "MCP-Protocol-Version", "Access-Control-Expose-Headers",
    ],
)

# ---- Mount MCP ----
if mcp_asgi:
    app.mount("/mcp", mcp_asgi)
    logger.info("Mounted MCP app at /mcp")
else:
    logger.warning("MCP not initialized; skipping mount.")

# ---- Upload Helper ----
def upload_blob_and_get_uri(bucket_name: str, source_file_name: str, destination_blob_name: str, project_id: Optional[str] = None):
    if storage is None:
        raise RuntimeError("google.cloud.storage not available.")
    client = storage.Client(project=project_id) if project_id else storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(source_file_name)
    return f"gs://{bucket_name}/{destination_blob_name}"

# ---- MCP Tools ----
os.makedirs("uploads", exist_ok=True)

if mcp:

    @mcp.tool
    def upload_pdf(filename: str, file_data: str, bucket_name: Optional[str] = None) -> dict:
        try:
            logger.info(f"upload_pdf called with filename: {filename}")
            if not filename.lower().endswith(".pdf"):
                return {"error": "Only PDFs allowed"}
            if "," in file_data and file_data.startswith("data:"):
                file_data = file_data.split(",", 1)[1]
            raw = base64.b64decode(file_data)
            local_path = os.path.join("uploads", filename)
            with open(local_path, "wb") as f:
                f.write(raw)
            
            logger.info(f"PDF saved locally: {local_path}")

            
            bucket = bucket_name or os.getenv("BUCKET_NAME") or "legal-doc-bucket1"
            project = os.getenv("PROJECT_ID") or "sodium-coil-470706-f4"
            gcs_uri = upload_blob_and_get_uri(bucket, local_path, filename, project)
            logger.info(f"PDF uploaded to GCS: {gcs_uri}")
            return {"message": "File uploaded to GCS", "gcs_uri": gcs_uri}
            
        except Exception as e:
            logger.exception("upload_pdf failed")
            return {"error": str(e)}

    @mcp.tool
    def pdf_qa(question: str, gsUri: str = None) -> dict:
        """
        Processes a question about a PDF and ensures the response is a dictionary.
        """
        try:
            logger.info(f"pdf_qa called with question: {question[:100]}... gsUri: {gsUri}")
            if not question:
                return {"error": "question required"}
            
            result = automated_chat(question, file_path=gsUri, stream_response=True, chat_history=None)
            
            # --- FIX IS HERE ---
            # Ensure the final output is always a dictionary.
            if isinstance(result, dict):
                # If the result is already a dict, ensure it has the 'answer' key for consistency
                if 'answer' in result:
                    return result
                # Try to find a common response key, otherwise convert the whole dict to a string
                raw_answer = result.get('response') or result.get('text') or str(result)
                return {"answer": raw_answer}
            elif isinstance(result, str):
                # If the result is a string, wrap it in a dictionary
                return {"answer": result}
            else:
                # For any other data type, convert to string and wrap
                return {"answer": str(result)}
                
        except Exception as e:
            logger.exception("pdf_qa failed")
            return {"error": str(e)}

    @mcp.tool
    def extract_text_from_pdf(gcs_uri: str) -> dict:
        """
        Extract text from a PDF document stored in Google Cloud Storage using Document AI.
        Returns structured text data with page-wise breakdown and form fields.
        
        Args:
            gcs_uri: The GCS URI of the PDF file (e.g., 'gs://bucket-name/file.pdf')
            
        Returns:
            dict: Contains extracted text, page details, form fields, and confidence score
        """
        try:
            logger.info(f"extract_text_from_pdf called with gcs_uri: {gcs_uri}")
            
            if not gcs_uri:
                return {"error": "gcs_uri required"}
            
            if not gcs_uri.startswith("gs://"):
                return {"error": "Invalid GCS URI format. Must start with 'gs://'"}
            
            # Process the PDF using Document AI
            result = process_pdf_with_document_ai(gcs_uri)
            
            if result["success"]:
                logger.info(f"OCR processing successful. Extracted {len(result['full_text'])} characters from {len(result['pages'])} pages")
                return {
                    "success": True,
                    "full_text": result["full_text"],
                    "pages": result["pages"],
                    "form_fields": result["form_fields"],
                    "confidence_score": result["confidence_score"],
                    "total_pages": len(result["pages"]),
                    "total_characters": len(result["full_text"])
                }
            else:
                logger.error(f"OCR processing failed: {result['error']}")
                return {"error": result["error"]}
                
        except Exception as e:
            logger.exception("extract_text_from_pdf failed")
            return {"error": str(e)}

    @mcp.tool
    def find_legal_precedents(clause: str, location: str = "US") -> dict:
        """
        Find relevant legal precedents for a given clause and jurisdiction.
        
        Args:
            clause: The legal clause text to find precedents for
            location: The jurisdiction/location (e.g., "US", "California", "India", "UK", "EU")
            
        Returns:
            dict: Contains the precedents analysis with case names, years, jurisdictions, and relevance explanations
        """
        try:
            logger.info(f"find_legal_precedents called with clause: {clause[:50]}... location: {location}")
            
            if not clause or not clause.strip():
                return {"error": "clause text is required"}
            
            if not location or not location.strip():
                location = "US"  # Default to US if no location provided
            
            # Call the precedent finding function
            precedents_result = find_precedents(clause.strip(), location.strip())
            
            if precedents_result:
                logger.info(f"Precedents found successfully for location: {location}")
                return {
                    "success": True,
                    "clause": clause,
                    "location": location,
                    "precedents": precedents_result,
                    "error": None
                }
            else:
                logger.warning("No precedents returned from find_precedents function")
                return {
                    "success": False,
                    "error": "No precedents found or analysis failed",
                    "clause": clause,
                    "location": location,
                    "precedents": ""
                }
                
        except Exception as e:
            logger.exception("find_legal_precedents failed")
            return {
                "success": False,
                "error": f"Precedent analysis failed: {str(e)}",
                "clause": clause,
                "location": location,
                "precedents": ""
            }

# ---- Debug Middleware ----
@app.middleware("http")
async def log_mcp_headers(request: Request, call_next):
    if request.url.path.startswith("/mcp"):
        logger.info("[incoming mcp request] %s %s headers=%s",
                    request.method, request.url.path,
                    {k: v for k, v in request.headers.items()
                     if k.lower() in ("host", "origin", "mcp-session-id")})
    response = await call_next(request)
    return response

# ---- Health ----
@app.get("/")
def root():
    return {"message": "LegalDemystifier Backend", "status": "running", "mcp_available": bool(mcp)}

@app.get("/health")
def health_check():
    return {"status": "ok", "mcp": bool(mcp)}

# ---- Startup ----
@app.on_event("startup")
async def on_startup():
    logger.info("Server starting. Allowed origins: %s", allowed_origins)

# ---- Entrypoint ----
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("mcp_app:app", host="0.0.0.0", port=int(os.getenv("PORT", 8080)), reload=True)