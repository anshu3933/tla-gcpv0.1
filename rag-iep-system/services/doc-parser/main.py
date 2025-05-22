import os
import json
import asyncio
import hashlib
from typing import Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from google.cloud import storage, pubsub_v1
from google.cloud.pubsub_v1.subscriber.message import Message
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langdetect import detect
import PyPDF2
import docx
import structlog

# Configure structured logging
logger = structlog.get_logger()

# Environment variables
PROJECT_ID = os.environ["PROJECT_ID"]
PROCESSED_BUCKET = os.environ["PROCESSED_BUCKET"]
PARSED_CHUNKS_TOPIC = os.environ["PUBSUB_PARSED_CHUNKS_TOPIC_ID"]

# Initialize clients
storage_client = storage.Client()
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, PARSED_CHUNKS_TOPIC)

# Language-specific chunk sizes
CHUNK_SIZES = {
    "en": 400,
    "fr": 200,
    "es": 300,
    "default": 400
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting doc-parser service")
    yield
    # Shutdown
    logger.info("Shutting down doc-parser service")

app = FastAPI(lifespan=lifespan)

class DocumentParser:
    def __init__(self):
        self.storage_client = storage_client
        self.publisher = publisher
        
    async def parse_pdf(self, blob: storage.Blob) -> List[str]:
        """Stream-parse PDF to avoid memory issues"""
        chunks = []
        
        with blob.open("rb") as pdf_file:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text = page.extract_text()
                
                if text.strip():
                    chunks.append(text)
                    
                # Yield control periodically
                if page_num % 10 == 0:
                    await asyncio.sleep(0)
                    
        return chunks
    
    async def parse_docx(self, blob: storage.Blob) -> List[str]:
        """Parse DOCX file"""
        chunks = []
        
        with blob.open("rb") as docx_file:
            doc = docx.Document(docx_file)
            
            for para in doc.paragraphs:
                if para.text.strip():
                    chunks.append(para.text)
                    
        return chunks
    
    def detect_language(self, text: str) -> str:
        """Detect text language"""
        try:
            return detect(text[:1000])  # Use first 1000 chars
        except:
            return "en"  # Default to English
    
    async def chunk_text(self, text: str, language: str) -> List[str]:
        """Adaptive chunking based on language"""
        chunk_size = CHUNK_SIZES.get(language, CHUNK_SIZES["default"])
        
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=50,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        
        return splitter.split_text(text)
    
    async def process_document(self, bucket_name: str, blob_name: str):
        """Main processing function"""
        logger.info("Processing document", bucket=bucket_name, blob=blob_name)
        
        # Get the blob
        bucket = self.storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        # Parse based on file type
        if blob_name.lower().endswith('.pdf'):
            raw_chunks = await self.parse_pdf(blob)
        elif blob_name.lower().endswith('.docx'):
            raw_chunks = await self.parse_docx(blob)
        else:
            raise ValueError(f"Unsupported file type: {blob_name}")
        
        # Combine and detect language
        full_text = "\n".join(raw_chunks)
        language = self.detect_language(full_text)
        
        # Chunk with language-specific settings
        chunks = await self.chunk_text(full_text, language)
        
        # Generate document ID
        doc_id = hashlib.md5(f"{bucket_name}/{blob_name}".encode()).hexdigest()
        
        # Save chunks to processed bucket
        processed_data = []
        for idx, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_{idx}"
            chunk_data = {
                "docId": doc_id,
                "chunkId": chunk_id,
                "sourceUri": f"gs://{bucket_name}/{blob_name}",
                "text": chunk,
                "language": language,
                "chunkIndex": idx,
                "totalChunks": len(chunks)
            }
            processed_data.append(chunk_data)
            
            # Publish to Pub/Sub
            future = self.publisher.publish(
                topic_path,
                json.dumps(chunk_data).encode('utf-8')
            )
            
            # Yield control periodically
            if idx % 10 == 0:
                await asyncio.sleep(0)
        
        # Save to processed bucket
        output_blob_name = f"{doc_id}.jsonl"
        output_bucket = self.storage_client.bucket(PROCESSED_BUCKET)
        output_blob = output_bucket.blob(output_blob_name)
        
        jsonl_content = "\n".join(json.dumps(item) for item in processed_data)
        output_blob.upload_from_string(jsonl_content)
        
        logger.info("Document processed", 
                   doc_id=doc_id, 
                   chunks=len(chunks),
                   language=language)

parser = DocumentParser()

@app.post("/process")
async def process_document(request: Request):
    """Pub/Sub push endpoint"""
    try:
        # Parse Pub/Sub message
        envelope = await request.json()
        message = envelope["message"]
        
        # Decode message
        data = json.loads(base64.b64decode(message["data"]).decode())
        
        # Extract bucket and object name
        bucket_name = data["bucket"]
        object_name = data["name"]
        
        # Process document
        await parser.process_document(bucket_name, object_name)
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error("Processing failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/healthz")
async def health():
    return {"status": "healthy"}

@app.get("/readyz")
async def ready():
    # Check dependencies
    try:
        # Test storage access
        list(storage_client.list_buckets(max_results=1))
        # Test Pub/Sub
        publisher.topic_path(PROJECT_ID, PARSED_CHUNKS_TOPIC)
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
