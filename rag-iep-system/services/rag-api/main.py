import os
import json
import hashlib
import asyncio
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from google.cloud import storage, firestore, secretmanager
from google.cloud import aiplatform
from vertexai.language_models import TextEmbeddingModel
from vertexai.generative_models import GenerativeModel
import firebase_admin
from firebase_admin import auth, credentials
import structlog

from shared.telemetry import (
    setup_telemetry,
    instrument_fastapi,
    create_span,
    get_trace_context,
)

logger = structlog.get_logger()

# Environment
PROJECT_ID = os.environ["PROJECT_ID"]
LOCATION = os.environ.get("LOCATION", "us-central1")
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", PROJECT_ID)
RAW_BUCKET = os.environ["RAW_BUCKET"]
INDEX_ENDPOINT_ID = os.environ["INDEX_ENDPOINT_ID"]
DEPLOYED_INDEX_ID = os.environ["DEPLOYED_INDEX_ID"]

# Initialize services
aiplatform.init(project=PROJECT_ID, location=LOCATION)
storage_client = storage.Client()
firestore_client = firestore.Client()
secret_client = secretmanager.SecretManagerServiceClient()

# Initialize Firebase Admin
firebase_admin.initialize_app(
    credential=credentials.ApplicationDefault(),
    options={"projectId": FIREBASE_PROJECT_ID},
)

# Load models once
embedding_model = TextEmbeddingModel.from_pretrained("textembedding-004")
generation_model = GenerativeModel("gemini-1.5-flash")

# Security
security = HTTPBearer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load prompt template
    app.state.prompt_template = await load_prompt_template()
    app.state.template_loaded_at = datetime.utcnow()

    # Set up telemetry
    app.state.tracer = setup_telemetry("rag-api")
    instrument_fastapi(app)

    logger.info("RAG API started", location=LOCATION)
    yield
    logger.info("RAG API shutting down")


app = FastAPI(lifespan=lifespan)


# Models
class DocumentUploadRequest(BaseModel):
    filename: str
    content_type: str
    content_md5: Optional[str] = None


class QueryRequest(BaseModel):
    question: str
    max_results: int = 5
    temperature: float = 0.7


class QueryResponse(BaseModel):
    answer: str
    sources: List[Dict]
    prompt_version: str


# Auth dependency
async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        decoded_token = auth.verify_id_token(credentials.credentials)
        return decoded_token
    except Exception as e:
        logger.error("Auth failed", error=str(e))
        raise HTTPException(status_code=401, detail="Invalid authentication")


# Prompt management
async def load_prompt_template() -> Dict:
    """Load prompt template from Firestore"""
    doc = firestore_client.collection("config").document("prompt_template").get()
    if doc.exists:
        return doc.to_dict()
    else:
        # Default template
        return {
            "version": "1.0.0",
            "template": """You are an AI assistant helping create Individualized Education Programs (IEPs).

Context documents:
{context}

Question: {question}

Instructions:
- Base your answer only on the provided context
- Be specific and cite relevant sections
- If the context doesn't contain relevant information, say so
- Format for clarity with appropriate sections

Answer:""",
        }


async def get_prompt_template(app: FastAPI) -> Dict:
    now = datetime.utcnow()
    if (
        not getattr(app.state, "template_loaded_at", None)
        or (now - app.state.template_loaded_at).total_seconds() > 300
    ):
        app.state.prompt_template = await load_prompt_template()
        app.state.template_loaded_at = now
    return app.state.prompt_template


@app.post("/documents", response_model=dict)
async def create_upload_url(request: DocumentUploadRequest, user=Depends(verify_token)):
    """Generate a signed URL for document upload"""
    try:
        # Generate unique blob name
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        user_id = user["uid"]
        safe_filename = request.filename.replace("/", "_")
        blob_name = f"{user_id}/{timestamp}_{safe_filename}"

        # Get blob reference
        bucket = storage_client.bucket(RAW_BUCKET)
        blob = bucket.blob(blob_name)

        # Generate signed URL with conditions
        conditions = [
            ["content-length-range", 0, 104857600],  # 100MB limit
        ]

        if request.content_type:
            conditions.append(["starts-with", "$Content-Type", request.content_type])

        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=30),
            method="PUT",
            content_md5=request.content_md5,
            if_generation_match=0,
            conditions=conditions,
        )

        return {
            "upload_url": url,
            "blob_name": blob_name,
            "expires_at": (datetime.utcnow() + timedelta(minutes=30)).isoformat(),
        }

    except Exception as e:
        logger.error("Failed to create upload URL", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reload-prompts")
async def reload_prompts(user=Depends(verify_token)):
    tmpl = await load_prompt_template()
    app.state.prompt_template = tmpl
    app.state.template_loaded_at = datetime.utcnow()
    return {"version": tmpl["version"]}


@app.post("/query")
async def query_rag(request: QueryRequest, user=Depends(verify_token)):
    """Main RAG query endpoint with streaming"""
    try:
        with create_span(
            "query_rag",
            {
                "user_id": user["uid"],
                "question_hash": hashlib.md5(request.question.encode()).hexdigest(),
            },
        ) as span:
            # 1. Embed the question
            with create_span("embed_question") as embed_span:
                question_embedding = embedding_model.get_embeddings([request.question])
                embed_span.set_attribute(
                    "embedding_dimensions", len(question_embedding[0].values)
                )

            # 2. Vector search
            with create_span("vector_search") as search_span:
                index_endpoint = aiplatform.MatchingEngineIndexEndpoint(
                    index_endpoint_name=INDEX_ENDPOINT_ID
                )

                response = index_endpoint.find_neighbors(
                    deployed_index_id=DEPLOYED_INDEX_ID,
                    queries=[question_embedding[0].values],
                    num_neighbors=request.max_results,
                )

                search_span.set_attribute(
                    "num_results", len(response[0]) if response[0] else 0
                )

            # Check if we have results
            if not response[0] or len(response[0]) == 0:
                tmpl = await get_prompt_template(app)
                return QueryResponse(
                    answer="I couldn't find any relevant information in the knowledge base for your question.",
                    sources=[],
                    prompt_version=tmpl["version"],
                )

            # 3. Retrieve chunk metadata from Firestore
            with create_span("retrieve_chunks") as chunks_span:
                chunks = []
                for neighbor in response[0]:
                    chunk_id = neighbor.id
                    distance = neighbor.distance

                    # Get metadata
                    doc = firestore_client.collection("chunks").document(chunk_id).get()
                    if doc.exists:
                        chunk_data = doc.to_dict()
                        chunk_data["relevance_score"] = 1 - distance
                        chunks.append(chunk_data)

                chunks_span.set_attribute("chunks_retrieved", len(chunks))

            # 4. Build context
            context = "\n\n".join(
                [f"[Source: {chunk['sourceUri']}]\n{chunk['text']}" for chunk in chunks]
            )

            # 5. Generate response
            tmpl = await get_prompt_template(app)
            prompt = tmpl["template"].format(context=context, question=request.question)

            # Log for debugging and evaluation
            logger.info(
                "RAG query",
                user_id=user["uid"],
                question_hash=hashlib.md5(request.question.encode()).hexdigest(),
                chunks_retrieved=len(chunks),
                prompt_version=tmpl["version"],
                **get_trace_context(),
            )

            # Stream response
            async def generate():
                with create_span("generate_response") as gen_span:
                    response = generation_model.generate_content(
                        prompt,
                        generation_config={
                            "temperature": request.temperature,
                            "max_output_tokens": 2048,
                        },
                        stream=True,
                    )

                    # Stream the response
                    full_response = ""
                    for chunk in response:
                        if chunk.text:
                            full_response += chunk.text
                            yield f"data: {json.dumps({'chunk': chunk.text})}\n\n"

                    # Send final message with sources
                    final_data = {
                        "done": True,
                        "sources": [
                            {"uri": c["sourceUri"], "score": c["relevance_score"]}
                            for c in chunks
                        ],
                        "prompt_version": tmpl["version"],
                    }
                    yield f"data: {json.dumps(final_data)}\n\n"

                    # Log token usage for cost tracking
                    estimated_tokens = (len(prompt) + len(full_response)) // 4
                    cost_micro_usd = int(estimated_tokens * 7)
                    cost_micro_usd = estimated_tokens * 0.000007

                    gen_span.set_attribute("estimated_tokens", estimated_tokens)
                    gen_span.set_attribute("cost_micro_usd", cost_micro_usd)

                    logger.info(
                        "LLM generation complete",
                        user_id=user["uid"],
                        estimated_tokens=estimated_tokens,
                        vertex_cost_micro_usd=cost_micro_usd,
                        **get_trace_context(),
                    )

            return StreamingResponse(generate(), media_type="text/event-stream")

    except Exception as e:
        logger.error(
            "Query failed", error=str(e), user_id=user.get("uid"), **get_trace_context()
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/healthz")
async def health():
    return {"status": "healthy"}


@app.get("/readyz")
async def ready():
    try:
        # Check Firestore
        firestore_client.collection("_health").document("check").set(
            {"ts": datetime.utcnow()}
        )
        # Check models loaded
        assert embedding_model is not None
        assert generation_model is not None
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
