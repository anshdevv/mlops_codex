import sys
from google import genai
from sentence_transformers import SentenceTransformer
import chromadb
from typing import List
from fastapi import FastAPI, HTTPException , Response
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector
import pandas as pd
import mlflow
import mlflow.pyfunc
import json
import os
import boto3
from dotenv import load_dotenv
from pydantic import BaseModel
import zipfile
import numpy as np
import re
from policy_engine import PolicyEngine, pii_detection_rule, prompt_injection_rule, toxicity_threshold_rule, hallucination_filter_rule
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Summary , Histogram



load_dotenv()

# Initialize the policy engine with rules
policy_engine = PolicyEngine(
    input_rules=[pii_detection_rule, prompt_injection_rule],
    output_rules=[toxicity_threshold_rule, hallucination_filter_rule]
)


collections = None
chroma_client = None
indexloaded = False
# ---- Load environment variables ----
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "eu-north-1")
S3_BUCKET = os.getenv("S3_BUCKET", "zameen-project")
S3_MODELS_PREFIX = os.getenv("S3_MODELS_PREFIX", "zameen_models")
S3_KEY = "chroma_joined_index.zip"
LOCAL_ZIP = "./chroma_joined_index_cloud.zip"
LOCAL_INDEX_PATH = "./chroma_joined_index_cloud"
# ---- Setup ----
app = FastAPI(title="Zameen MLOps API")
REQUEST_COUNT = Counter("llm_requests_total", "Total LLM requests")
LATENCY = Histogram("llm_request_latency_seconds", "LLM request latency")
TOKEN_USAGE = Counter("llm_tokens_total", "Total tokens processed")
COST = Counter("llm_cost_total", "Total cost in USD")
GUARDRAIL_VIOLATIONS = Counter("llm_guardrail_violations_total", "Total guardrail violations")
# Example usage in an endpoint (add to your endpoint logic as needed):
# input_result = policy_engine.validate_input(user_input)
# if not input_result['passed']:
#     raise HTTPException(status_code=400, detail=input_result['reason'])
# output_result = policy_engine.moderate_output(model_output)
# if not output_result['passed']:
#     raise HTTPException(status_code=400, detail=output_result['reason'])

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- AWS + MLflow Config ----

googlemodel = genai.Client()





# Initialize S3 client (will use env creds)
s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_DEFAULT_REGION,
)

# MLflow setup
mlflow.set_tracking_uri("http://127.0.0.1:5000")
model_name = "ZameenPriceModelV2"
stage = "Production"

def downloadindex():
    global chroma_client , collections
    if os.path.exists(LOCAL_INDEX_PATH):

        print("📦 Local Chroma index already exists. Skipping download.")
        return
    
    print("⬇️ Downloading Chroma index from S3...")
    s3 = boto3.client("s3")
    s3.download_file(S3_BUCKET, S3_KEY, LOCAL_ZIP)

    print("📂 Extracting zip...")
    with zipfile.ZipFile(LOCAL_ZIP, 'r') as z:
        z.extractall(".")
    
    print("✅ Index ready.")
    chroma_client = chromadb.PersistentClient(path="./chroma_joined_index")
    collections = chroma_client.get_collection("zameen_joined_index")
    

downloadindex()
embmodel = SentenceTransformer("all-MiniLM-L6-v2")

# ---- DB Connection ----
def get_connection():
    return mysql.connector.connect(
        host=os.getenv("HOST"),
        port=int(os.getenv("PORT", 3306)),
        user=os.getenv("USER"),
        password=os.getenv("PASSWORD"),
        database=os.getenv("DB_NAME"),
    )


# ---- Load model ----
def load_model(model_name="ZameenPriceModelSale"):
    model = None
    sale_feature_columns = None
    valid_metadata = None

    try:
        os.makedirs("model_cache", exist_ok=True)

        # Download entire model folder
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(
            Bucket=S3_BUCKET, Prefix=f"{S3_MODELS_PREFIX}/{model_name}"
        ):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                rel_path = os.path.relpath(key, f"{S3_MODELS_PREFIX}/{model_name}")
                local_path = os.path.join("model_cache", model_name, rel_path)
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                s3.download_file(S3_BUCKET, key, local_path)

        # Download metadata
        s3.download_file(
            S3_BUCKET,
            f"{S3_MODELS_PREFIX}/feature_columns.json",
            "model_cache/feature_columns.json",
        )
        s3.download_file(
            S3_BUCKET,
            f"{S3_MODELS_PREFIX}/valid_metadata.json",
            "model_cache/valid_metadata.json",
        )

        # Load with MLflow
        model = mlflow.sklearn.load_model(f"model_cache/{model_name}")

        with open("model_cache/feature_columns.json", "r") as f:
            feat = json.load(f)
        with open("model_cache/valid_metadata.json", "r") as f:
            valid_metadata = json.load(f)

        sale_feature_columns = feat.get("sale", [])
        print("✅ Model and artifacts loaded from S3 successfully!")

    except Exception as e:
        print(f"❌ Model load failed: {e}")

    return model, sale_feature_columns, valid_metadata


model, sale_feature_columns, valid_metadata = load_model()

# ---- Load location/property types ----
locations = []
propertyTypes = []


def load_location_and_property_types():
    global locations, propertyTypes
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT DISTINCT prop_type, location FROM property_data")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        locations = sorted({r["location"] for r in rows if r.get("location")})
        propertyTypes = sorted({r["prop_type"] for r in rows if r.get("prop_type")})

        return {"locations": locations, "prop_type": propertyTypes}
    except Exception as e:
        print(f" Failed to load locations/property types from DB: {e}")
        return {"locations": [], "prop_type": []}


load_location_and_property_types()


# ---- Routes ----
@app.get("/")
def home():
    return {"message": "Zameen API is running"}


@app.get("/listings")
def get_listings(
    limit: int = 20,
    location: str | None = None,
    prop_type: str | None = None,
    purpose: str | None = None,  # "sale" or "rent"
    min_price: float | None = None,
    max_price: float | None = None,
):
    """
    Return property listings with optional filtering applied in the database.

    Supported filters (all optional):
    - location: exact match on location column
    - prop_type: exact match on prop_type column
    - purpose: "sale" / "rent"
    - min_price / max_price: numeric price range
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
        SELECT prop_type, purpose, covered_area, price, location, beds, baths
        FROM property_data
        WHERE 1=1
    """
    params: list = []

    if location:
        query += " AND location = %s"
        params.append(location)

    if prop_type:
        query += " AND prop_type = %s"
        params.append(prop_type)

    if purpose:
        query += " AND purpose = %s"
        params.append(purpose)

    if min_price is not None:
        query += " AND price >= %s"
        params.append(min_price)

    if max_price is not None:
        query += " AND price <= %s"
        params.append(max_price)

    query += " LIMIT %s"
    params.append(limit)

    cursor.execute(query, tuple(params))
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return data


@app.get("/locations")
def get_locations(purpose: str = "sale"):
    data = load_location_and_property_types()
    return {"locations": data["locations"]}


@app.get("/prop_type")
def get_prop_type(purpose: str = "sale"):
    data = load_location_and_property_types()
    return {"prop_type": data["prop_type"]}


# ---- Prediction Schema ----
class PredictionInput(BaseModel):
    coveredArea: float
    beds: int
    bathrooms: int
    location: str
    propType: str
    purpose: str = "sale"


@app.post("/predict")
async def predict_price(input_data: PredictionInput):
    if model is None:
        raise HTTPException(
            status_code=500,
            detail="Model not loaded. Check MLflow server and registry.",
        )

    valid_data = load_location_and_property_types()

    if input_data.location not in valid_data["locations"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid location. Must be one of: {', '.join(valid_data['locations'])}",
        )

    if input_data.propType not in valid_data["prop_type"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid property type. Must be one of: {', '.join(valid_data['prop_type'])}",
        )

    try:
        base_df = pd.DataFrame(
            [[input_data.coveredArea, input_data.beds, input_data.bathrooms]],
            columns=["covered_area", "beds", "baths"],
        )

        loc_df = pd.get_dummies(pd.Series([input_data.location]), prefix="location")
        prop_df = pd.get_dummies(pd.Series([input_data.propType]), prefix="prop_type")
        input_df = pd.concat([base_df, loc_df, prop_df], axis=1)

        # Align columns
        if sale_feature_columns:
            for col in sale_feature_columns:
                if col not in input_df.columns:
                    input_df[col] = 0
            input_df = input_df[sale_feature_columns]
        else:
            input_df = input_df.fillna(0)

        predicted_price = float(model.predict(input_df)[0])
        return {
            "prediction": predicted_price,
            "formatted_price": f"PKR {predicted_price:,.2f}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")


@app.get("/health")
def health_check():
    return {"status": "ok"}


def cosine_similarity(a, b):
    """Compute cosine similarity between two vectors with zero-division protection."""
    a = np.array(a)
    b = np.array(b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return np.dot(a, b) / (norm_a * norm_b)


def retrieve(query: str, n_results: int = 20, top_k: int = 7):
    """
    Enhanced RAG retrieval with advanced reranking:
    - Hybrid scoring: semantic similarity + keyword matching
    - Metadata-aware boosting
    - Diversity filtering to avoid redundant results
    """
    try:
        # Encode query
        query_emb = embmodel.encode([query])[0]
        query_lower = query.lower()
        query_words = set(query_lower.split())

        # Retrieve initial results from Chroma (get more for better reranking)
        results = collections.query(
            query_embeddings=[query_emb.tolist()],
            n_results=n_results
        )

        docs = results["documents"][0]
        metas = results["metadatas"][0]
        ids = results.get("ids", [None] * len(docs))[0] if results.get("ids") else [None] * len(docs)

        if not docs:
            return {"documents": [], "metadatas": [], "scores": []}

        # Enhanced reranking with multiple signals
        doc_embeddings = embmodel.encode(docs)
        semantic_scores = [cosine_similarity(query_emb, d_emb) for d_emb in doc_embeddings]
        
        # Keyword matching boost (simple TF-based)
        keyword_boosts = []
        for doc in docs:
            doc_lower = doc.lower()
            doc_words = set(doc_lower.split())
            # Count matching keywords
            matches = len(query_words.intersection(doc_words))
            # Normalize by query length
            keyword_score = matches / max(len(query_words), 1) if query_words else 0
            keyword_boosts.append(keyword_score * 0.2)  # 20% boost max
        
        # Metadata boost (if location/property type matches query)
        metadata_boosts = []
        for meta in metas:
            meta_boost = 0.0
            if meta:
                meta_str = " ".join(str(v).lower() for v in meta.values() if v)
                meta_words = set(meta_str.split())
                meta_matches = len(query_words.intersection(meta_words))
                meta_boost = (meta_matches / max(len(query_words), 1)) * 0.15 if query_words else 0
            metadata_boosts.append(meta_boost)
        
        # Combined scoring: semantic (70%) + keyword (20%) + metadata (10%)
        combined_scores = [
            (sem * 0.7) + (kw * 0.2) + (meta * 0.1)
            for sem, kw, meta in zip(semantic_scores, keyword_boosts, metadata_boosts)
        ]

        # Sort by combined score
        ranked = sorted(zip(docs, metas, ids, combined_scores, semantic_scores), 
                       key=lambda x: x[3], reverse=True)
        
        # Diversity filtering: avoid very similar documents
        final_docs = []
        final_metas = []
        final_scores = []
        seen_content = set()
        
        for doc, meta, doc_id, comb_score, sem_score in ranked:
            # Simple deduplication: skip if very similar content already selected
            doc_snippet = doc[:100].lower().strip()
            if doc_snippet not in seen_content:
                final_docs.append(doc)
                final_metas.append(meta)
                final_scores.append(comb_score)
                seen_content.add(doc_snippet)
                
                if len(final_docs) >= top_k:
                    break

        return {
            "documents": final_docs,
            "metadatas": final_metas,
            "scores": final_scores
        }
    except Exception as e:
        print(f"❌ Retrieval Error: {e}")
        import traceback
        traceback.print_exc()
        return {"documents": [], "metadatas": [], "scores": []}


class ChatMessage(BaseModel):
    role: str   # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]


def extract_property_data(doc: str) -> dict:
    """Extract structured property data from document text for mathematical operations and sentiment analysis."""
    data = {}
    try:
        # Try to extract price
        price_match = re.search(r'price[:\s]+([\d,]+)', doc, re.IGNORECASE)
        if price_match:
            data['price'] = float(price_match.group(1).replace(',', ''))
        
        # Extract area
        area_match = re.search(r'(?:area|covered_area|size)[:\s]+([\d.]+)', doc, re.IGNORECASE)
        if area_match:
            data['area'] = float(area_match.group(1))
        
        # Extract beds/baths
        beds_match = re.search(r'bed[s]?[:\s]+(\d+)', doc, re.IGNORECASE)
        if beds_match:
            data['beds'] = int(beds_match.group(1))
        
        baths_match = re.search(r'bath[s]?[:\s]+(\d+)', doc, re.IGNORECASE)
        if baths_match:
            data['baths'] = int(baths_match.group(1))
        
        # Extract location
        location_match = re.search(r'location[:\s]+([A-Za-z\s,]+)', doc, re.IGNORECASE)
        if location_match:
            data['location'] = location_match.group(1).strip()
        
        # Extract property type
        prop_type_match = re.search(r'(?:type|prop_type)[:\s]+([A-Za-z\s]+)', doc, re.IGNORECASE)
        if prop_type_match:
            data['prop_type'] = prop_type_match.group(1).strip()
        
        # Extract sentiment information if present
        sentiment_keywords = ['water_sentiment', 'electricity_sentiment', 'gas_sentiment', 'traffic_sentiment', 'safety_sentiment']
        for keyword in sentiment_keywords:
            pattern = rf'{keyword}[:\s]+(good|fair|poor)', re.IGNORECASE
            match = re.search(pattern, doc)
            if match:
                data[keyword] = match.group(1).capitalize()
    except:
        pass
    return data


def build_property_cards(bundles: List[dict]) -> List[dict]:
    """
    Prepare structured card data for up to three properties.
    Only returns cards when we have at least some numeric signal (price/area/beds/baths)
    to avoid showing empty / meaningless cards.
    """
    cards: List[dict] = []
    for idx, bundle in enumerate(bundles):
        data = bundle.get("data") or {}
        doc = bundle.get("doc", "")
        if not data:
            continue

        price = data.get("price")
        area = data.get("area")
        beds = data.get("beds")
        baths = data.get("baths")

        # Skip if we have no meaningful structured info at all
        if price is None and area is None and beds is None and baths is None:
            continue

        price_per_area = (price / area) if price and area and area != 0 else None

        cards.append(
            {
                "id": bundle.get("meta", {}).get("id") or f"property_{idx+1}",
                "label": data.get("prop_type") or f"Property {idx+1}",
                "location": data.get("location"),
                "price": price,
                "area": area,
                "beds": beds,
                "baths": baths,
                "price_per_area": price_per_area,
                "score": bundle.get("score"),
                "snippet": doc[:280],
            }
        )

        if len(cards) == 3:
            break

    return cards


def build_comparison_insights(cards: List[dict]) -> str:
    """Produce textual insights (cheapest, best value, etc.) for prompt guidance."""
    if not cards:
        return "Not enough structured data for comparison."

    insights = []
    priced = [c for c in cards if isinstance(c.get("price"), (int, float))]
    areas = [c for c in cards if isinstance(c.get("area"), (int, float))]
    value_props = [c for c in cards if isinstance(c.get("price_per_area"), (int, float))]

    if priced:
        cheapest = min(priced, key=lambda x: x["price"])
        insights.append(
            f"Cheapest option: {cheapest['label']} at PKR {cheapest['price']:,.0f}"
        )
    if priced:
        premium = max(priced, key=lambda x: x["price"])
        insights.append(
            f"Highest budget option: {premium['label']} at PKR {premium['price']:,.0f}"
        )
    if areas:
        largest = max(areas, key=lambda x: x["area"])
        insights.append(
            f"Largest covered area: {largest['label']} with {largest['area']} units"
        )
    if value_props:
        best_value = min(value_props, key=lambda x: x["price_per_area"])
        insights.append(
            f"Best price/area: {best_value['label']} at PKR {best_value['price_per_area']:,.0f} per unit"
        )

    if not insights:
        return "Structured comparison unavailable."

    return "\n".join(insights)


def generate_chat_response(messages: List[ChatMessage]) -> dict:
    """
    Enhanced chat response generation with:
    - Advanced reasoning capabilities
    - Mathematical sorting and calculations
    - Better context memory (extracts key facts)
    - Conversational tone with context awareness
    - Structured payload for frontend cards
    """
    try:
        # 1. Get last user message
        last_user = messages[-1].content

        # 2. Check for duplicate user query
        user_messages = [m.content for m in messages if m.role == "user"]
        if len(user_messages) > 1 and user_messages[-1] == user_messages[-2]:
            return {
                "text": "I just answered that question. Would you like more details or a different question?",
                "properties": [],
            }

        # 3. Enhanced context memory: keep last 10 messages + extract key facts
        recent_messages = messages[-10:] if len(messages) > 10 else messages
        conversation_history = "\n".join(
            f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}"
            for m in recent_messages[:-1]  # Exclude current message
        )

        # Extract key facts from conversation (locations, preferences, budgets mentioned)
        key_facts = []
        for msg in recent_messages:
            content_lower = msg.content.lower()
            # Extract mentioned locations or budgets heuristically
            if any(word in content_lower for word in ["location", "area", "place", "budget", "price", "in "]):
                key_facts.append(f"User mentioned: {msg.content[:120]}")

        key_facts_str = "\n".join(key_facts[-4:]) if key_facts else "No specific preferences mentioned yet."

        # 4. Enhanced Query Rewriting with context awareness
        rewrite_prompt = f"""You are helping rewrite a user query for property search.

Conversation context (excluding the latest user turn):
{conversation_history}

Key facts extracted:
{key_facts_str}

Current user message: "{last_user}"

Rewrite this into an optimal search query for finding property listings. Include relevant context from the conversation.
Return ONLY the rewritten query, nothing else."""

        # Use callWrapper for query rewriting (guardrails + logging)
        rewrite_result = callWrapper(rewrite_prompt)
        if "Input Guardrail Violation" in rewrite_result["response"] or "Output Guardrail Violation" in rewrite_result["response"]:
            return {"text": rewrite_result["response"], "properties": []}
        rewritten_query = rewrite_result["response"] if rewrite_result["response"] else last_user

        # 5. Enhanced RAG Retrieval
        rag_results = retrieve(rewritten_query, n_results=20, top_k=7)
        context_docs = rag_results["documents"]
        context_scores = rag_results["scores"]
        context_metas = rag_results.get("metadatas", []) or []

        # Bundle documents with structured data and extract sentiment info
        bundled_results = []
        formatted_context_parts = []
        sentiment_info = []

        for idx, doc in enumerate(context_docs):
            score = context_scores[idx] if idx < len(context_scores) else 0.0
            meta = context_metas[idx] if idx < len(context_metas) else {}
            prop_data = extract_property_data(doc)
            bundle = {"doc": doc, "score": score, "meta": meta or {}, "data": prop_data}
            bundled_results.append(bundle)

            # Extract sentiment information from document (look for sentiment keywords)
            doc_lower = doc.lower()
            if any(word in doc_lower for word in ['sentiment', 'water', 'electricity', 'gas', 'traffic', 'safety', 'good', 'fair', 'poor']):
                # Try to extract location for sentiment mapping
                location = prop_data.get("location") or meta.get("location", "")
                if location:
                    sentiment_info.append(f"Location: {location} - Sentiment data available in document")

            info_parts = [f"Document {idx + 1} (relevance: {score:.3f})"]
            if prop_data.get("price"):
                info_parts.append(f"Price: PKR {prop_data['price']:,.0f}")
            if prop_data.get("area"):
                info_parts.append(f"Area: {prop_data['area']} sq units")
            if prop_data.get("location"):
                info_parts.append(f"Location: {prop_data['location']}")
            if prop_data.get("beds"):
                info_parts.append(f"Beds: {prop_data['beds']}")
            if prop_data.get("baths"):
                info_parts.append(f"Baths: {prop_data['baths']}")

            formatted_context_parts.append(
                f"{' | '.join(info_parts)}\nContent: {doc[:600]}"
            )

        context = (
            "\n\n---\n\n".join(formatted_context_parts)
            if formatted_context_parts
            else "[No relevant documents found. Use general knowledge.]"
        )

        structured_cards = build_property_cards(bundled_results)
        comparison_summary = build_comparison_insights(structured_cards)

        # 6. Determine if context is useful
        avg_score = np.mean(context_scores) if context_scores else 0.0
        use_context = avg_score > 0.25  # Lower threshold for better coverage

        # 7. Enhanced LLM prompt with reasoning, mathematical capabilities, and sentiment awareness
        sentiment_context = "\n".join(sentiment_info) if sentiment_info else "No specific sentiment data found in retrieved documents."

        main_prompt = f"""You are Zameen.com's intelligent property assistant. You are conversational, helpful, and have strong reasoning abilities.

CAPABILITIES:
- Mathematical reasoning: Calculate price per square unit, compare properties, sort by value
- Context awareness: Remember previous conversation and user preferences
- Data analysis: Extract and compare property features from retrieved documents
- Sentiment analysis: Include location sentiments (water, electricity, gas, traffic, safety) when available
- Natural conversation: Respond like a knowledgeable real estate expert

{"RETRIEVED PROPERTY DATA:" if use_context else "LIMITED DATA - use general knowledge:"}
{context if use_context else "[No specific property data available. Provide general guidance based on real estate knowledge.]"}

LOCATION SENTIMENTS (if available):
{sentiment_context}

COMPARISON INSIGHTS (use for detailed comparisons):
{comparison_summary}

CONVERSATION HISTORY:
{conversation_history}

KEY FACTS FROM CONVERSATION:
{key_facts_str}

CURRENT USER MESSAGE:
{last_user}
        
INSTRUCTIONS:
1. If the user asks to compare, sort, or calculate (e.g., "cheapest", "best value", "price per sq ft"), use the retrieved property data to perform mathematical operations
2. Extract numbers from documents: prices, areas, beds, baths
3. Calculate metrics like price per square unit when relevant
4. Sort properties mathematically when asked (by price, area, value, etc.)
5. When comparing properties, provide detailed comparisons including:
   - Price differences and value analysis
   - Size and space comparisons
   - Location advantages/disadvantages
   - Sentiment information (water, electricity, gas, traffic, safety) when available in the context
6. Be conversational - reference previous parts of the conversation naturally
7. If data is available, cite specific numbers and properties with clear reasoning
8. Show your mathematical reasoning: explain how you calculated or compared values
9. Include sentiment information when discussing locations - mention water, electricity, gas, traffic, and safety conditions if found in the retrieved documents
10. Format your response with clear paragraphs and use bullet points for comparisons when listing multiple properties
11. If the user asks about locations/types not in context, acknowledge it and provide general guidance

RESPOND AS ASSISTANT:
Provide a comprehensive, well-formatted response that:
- Answers the user's question directly and conversationally
- Includes specific numbers and calculations when comparing properties
- Mentions location sentiments (water, electricity, gas, traffic, safety) when available
- Uses clear paragraphs and bullet points for readability
- Shows mathematical reasoning for any calculations or comparisons"""

        # Use callWrapper for final answer (guardrails + logging)
        answer_result = callWrapper(main_prompt)
        if "Input Guardrail Violation" in answer_result["response"] or "Output Guardrail Violation" in answer_result["response"]:
            return {"text": answer_result["response"], "properties": []}
        generated = answer_result["response"] if answer_result["response"] else "Sorry, no response generated."

        # Final duplicate check
        recent_assistant = [m.content for m in reversed(messages) if m.role == "assistant"]
        if recent_assistant and recent_assistant[0].strip() == generated.strip():
            generated = "I've already provided that information. Would you like me to expand on a specific aspect or help with something else?"

        # Don't send cards - just use comparison data for better text responses
        return {"text": generated, "properties": []}

    except Exception as e:
        print(f"❌ Chat Error: {e}")
        import traceback

        traceback.print_exc()
        return {
            "text": "Sorry, I encountered an error. Please try again.",
            "properties": [],
        }


@LATENCY.time()
def callWrapper(prompt:str):
    REQUEST_COUNT.inc()
    promptpass = policy_engine.validate_input(prompt)
    if not promptpass['passed']:
        GUARDRAIL_VIOLATIONS.inc()
        return {
        "response":  f"Input Guardrail Violation: {promptpass['reason']}",
        "properties": [],  # No cards - all info in text response
    }
    else:
        response = googlemodel.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        ).text.strip()
        outputpass = policy_engine.moderate_output(response)
        if not outputpass['passed']:
            GUARDRAIL_VIOLATIONS.inc()
            return {
            "response":  f"Output Guardrail Violation: {outputpass['reason']}",
            "properties": [],  # No cards - all info in text response
        }
        else:
            return {
            "response": response,
            "properties": [],  # No cards - all info in text response
        }
      
    
@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)    


@app.post("/chat")
def chat(req: ChatRequest):
    """Chat endpoint - returns a SINGLE high-quality text response per request."""
    payload = generate_chat_response(req.messages)
    return {
        "response": payload.get("text"),
        "properties": [],  # No cards - all info in text response
    }
