import os
import json
import asyncio
from typing import List, Dict
from datetime import datetime
import time

from fastapi import FastAPI, HTTPException
from google.cloud import pubsub_v1
from google.cloud import aiplatform
from google.cloud import storage
import structlog
from contextlib import asynccontextmanager

logger = structlog.get_logger()

# Environment
PROJECT_ID = os.environ["PROJECT_ID"]
LOCATION = os.environ.get("LOCATION", "us-central1")
PARSED_CHUNKS_TOPIC = os.environ["PUBSUB_PARSED_CHUNKS_TOPIC_ID"]
VECTOR_UPSERTS_BUCKET = os.environ.get("VECTOR_UPSERTS_BUCKET", f"{PROJECT_ID}-vector-upserts")
EMBEDDING_MODEL = "textembedding-004"
BATCH_SIZE = 100
BATCH_TIMEOUT = 10  # seconds

# Initialize clients at module level
aiplatform.init(project=PROJECT_ID, location=LOCATION)
storage_client = storage.Client()

# Load embedding model once
from vertexai.language_models import TextEmbeddingModel
embedding_model = TextEmbeddingModel.from_pretrained(EMBEDDING_MODEL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting embedder service", 
                model=EMBEDDING_MODEL,
                location=LOCATION)
    
    # Start batch processor
    app.state.batch_processor = BatchProcessor()
    asyncio.create_task(app.state.batch_processor.run())
    
    yield
    
    # Shutdown
    logger.info("Shutting down embedder service")
    app.state.batch_processor.stop()

app = FastAPI(lifespan=lifespan)

class BatchProcessor:
    def __init__(self):
        self.queue = asyncio.Queue(maxsize=1000)
        self.running = True
        self.subscriber = pubsub_v1.SubscriberClient()
        self.subscription_path = self.subscriber.subscription_path(
            PROJECT_ID, f"{PARSED_CHUNKS_TOPIC}-embedder-sub"
        )
        
    async def run(self):
        """Main batch processing loop"""
        while self.running:
            try:
                # Collect batch
                batch = []
                start_time = time.time()
                
                while len(batch) < BATCH_SIZE and (time.time() - start_time) < BATCH_TIMEOUT:
                    try:
                        # Non-blocking get with timeout
                        timeout = BATCH_TIMEOUT - (time.time() - start_time)
                        message = await asyncio.wait_for(
                            self.queue.get(), 
                            timeout=max(0.1, timeout)
                        )
                        batch.append(message)
                    except asyncio.TimeoutError:
                        break
                
                if batch:
                    await self.process_batch(batch)
                    
            except Exception as e:
                logger.error("Batch processing error", error=str(e))
                await asyncio.sleep(1)
    
    async def process_batch(self, messages: List[Dict]):
        """Process a batch of messages"""
        start_time = time.time()
        
        try:
            # Extract texts
            texts = [msg["text"] for msg in messages]
            
            # Get embeddings in batch
            embeddings = embedding_model.get_embeddings(texts)
            
            # Prepare vector data
            vector_data = []
            for msg, embedding in zip(messages, embeddings):
                vector_data.append({
                    "id": msg["chunkId"],
                    "embedding": embedding.values,
                    "metadata": {
                        "docId": msg["docId"],
                        "sourceUri": msg["sourceUri"],
                        "language": msg["language"],
                        "chunkIndex": msg["chunkIndex"]
                    }
                })
            
            # Save to GCS for batch upsert
            await self.save_vector_batch(vector_data)
            
            # Log metrics
            duration = time.time() - start_time
            logger.info("Batch processed",
                       batch_size=len(messages),
                       duration_ms=int(duration * 1000),
                       tokens_per_second=len(texts) / duration)
            
        except Exception as e:
            logger.error("Batch embedding failed", 
                        error=str(e),
                        batch_size=len(messages))
            # Could implement retry logic here
    
    async def save_vector_batch(self, vector_data: List[Dict]):
        """Save vectors to GCS for batch upsert"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"batch_{timestamp}.jsonl"
        
        bucket = storage_client.bucket(VECTOR_UPSERTS_BUCKET)
        blob = bucket.blob(filename)
        
        # Convert to JSONL
        jsonl_content = "\n".join(json.dumps(item) for item in vector_data)
        
        # Upload
        blob.upload_from_string(jsonl_content)
        
        logger.info("Vector batch saved", 
                   filename=filename,
                   vectors=len(vector_data))
    
    def stop(self):
        self.running = False

# Pub/Sub message handler
@app.post("/messages")
async def handle_message(request: Request):
    """Handle Pub/Sub push messages"""
    try:
        envelope = await request.json()
        message = envelope["message"]
        
        # Decode message
        data = json.loads(base64.b64decode(message["data"]).decode())
        
        # Add to queue
        await app.state.batch_processor.queue.put(data)
        
        return {"status": "queued"}
        
    except Exception as e:
        logger.error("Message handling failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/healthz")
async def health():
    return {"status": "healthy"}

@app.get("/readyz")
async def ready():
    try:
        # Check if model is loaded
        assert embedding_model is not None
        # Check queue
        assert app.state.batch_processor.queue is not None
        return {"status": "ready"}
    except:
        raise HTTPException(status_code=503, detail="Not ready")
