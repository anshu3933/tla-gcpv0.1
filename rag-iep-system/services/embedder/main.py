import os
import json
import asyncio
import base64
from typing import List, Dict
from datetime import datetime
import time

from fastapi import FastAPI, HTTPException
from google.cloud import pubsub_v1
from google.cloud import aiplatform
from google.cloud import storage, firestore
import structlog
from contextlib import asynccontextmanager
from shared.telemetry import setup_telemetry, instrument_fastapi

logger = structlog.get_logger()

# Environment
PROJECT_ID = os.environ["PROJECT_ID"]
LOCATION = os.environ.get("LOCATION", "us-central1")
PARSED_CHUNKS_TOPIC = os.environ["PUBSUB_PARSED_CHUNKS_TOPIC_ID"]
VECTOR_UPSERTS_BUCKET = os.environ.get(
    "VECTOR_UPSERTS_BUCKET", f"{PROJECT_ID}-vector-upserts"
)
EMBEDDING_MODEL = "textembedding-004"
BATCH_SIZE = 100
BATCH_TIMEOUT = 10  # seconds

# Initialize clients at module level
aiplatform.init(project=PROJECT_ID, location=LOCATION)
storage_client = storage.Client()
firestore_client = firestore.Client()

# Load embedding model once
from google.cloud.aiplatform import TextEmbeddingModel

embedding_model = TextEmbeddingModel.from_pretrained(EMBEDDING_MODEL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.tracer = setup_telemetry("embedder")
    instrument_fastapi(app)
    logger.info(
        "Starting embedder service",
        model=EMBEDDING_MODEL,
        location=LOCATION,
    )

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
        self.running = True
        self.subscriber = pubsub_v1.SubscriberClient()
        self.subscription_path = self.subscriber.subscription_path(
            PROJECT_ID, f"{PARSED_CHUNKS_TOPIC}-embedder-sub"
        )

    def handle_message(self, message: pubsub_v1.subscriber.message.Message):
        try:
            data = json.loads(base64.b64decode(message.data).decode())
            asyncio.create_task(self.process_batch([data]))
            message.ack()
        except Exception as e:
            logger.error("Message processing failed", error=str(e))
            message.nack()

    async def run(self):
        """Pull messages directly from Pub/Sub"""
        flow_control = pubsub_v1.types.FlowControl(max_messages=BATCH_SIZE)

        future = self.subscriber.subscribe(
            self.subscription_path,
            callback=self.handle_message,
            flow_control=flow_control,
        )
        while self.running:
            await asyncio.sleep(1)
        future.cancel()

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
                vector_data.append(
                    {
                        "id": msg["chunkId"],
                        "embedding": embedding.values,
                        "metadata": {
                            "docId": msg["docId"],
                            "sourceUri": msg["sourceUri"],
                            "language": msg["language"],
                            "chunkIndex": msg["chunkIndex"],
                        },
                    }
                )

                # Write metadata document
                firestore_client.collection("chunks").document(msg["chunkId"]).set(
                    {
                        "docId": msg["docId"],
                        "text": msg["text"],
                        "sourceUri": msg["sourceUri"],
                        "language": msg["language"],
                        "chunkIndex": msg["chunkIndex"],
                    }
                )

            # Save to GCS for batch upsert
            await self.save_vector_batch(vector_data)

            # Log metrics
            duration = time.time() - start_time
            logger.info(
                "Batch processed",
                batch_size=len(messages),
                duration_ms=int(duration * 1000),
                tokens_per_second=len(texts) / duration,
            )

        except Exception as e:
            logger.error(
                "Batch embedding failed", error=str(e), batch_size=len(messages)
            )
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

        logger.info("Vector batch saved", filename=filename, vectors=len(vector_data))

    def stop(self):
        self.running = False


@app.get("/healthz")
async def health():
    return {"status": "healthy"}


@app.get("/readyz")
async def ready():
    try:
        # Check if model is loaded
        assert embedding_model is not None
        return {"status": "ready"}
    except:
        raise HTTPException(status_code=503, detail="Not ready")
