
import sys
import requests
from sentence_transformers import SentenceTransformer
import chromadb
from typing import List
from fastapi import FastAPI, HTTPException , Body ,Path
from fastapi.middleware.cors import CORSMiddleware
import pymysql
import json
import os
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv
from pydantic import BaseModel
import zipfile
import numpy as np
import re
import logging
import boto3
from huggingface_hub import InferenceClient
from policy_engine import PolicyEngine, pii_detection_rule, prompt_injection_rule, toxicity_threshold_rule, hallucination_filter_rule

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('app.log')
    ]
)



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
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "property-hub")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
BLOB_KEY = "chroma_joined_index.zip"
LOCAL_ZIP = "./chroma_joined_index_cloud.zip"
LOCAL_INDEX_PATH = "./chroma_joined_index_cloud"

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "eu-north-1")
S3_BUCKET = os.getenv("S3_BUCKET", "zameen-project")
S3_MODELS_PREFIX = os.getenv("S3_MODELS_PREFIX", "zameen_models")
S3_KEY = "chroma_joined_index.zip"
LOCAL_ZIP = "./chroma_joined_index_cloud.zip"
LOCAL_INDEX_PATH = "./chroma_joined_index_cloud"
# ---- Setup ----
app = FastAPI(title="Property Hub API")

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Azure & Hugging Face Config ----

# Hugging Face Inference API config

HF_API_KEY = os.getenv("HF_API_KEY")
HF_MODEL = "Qwen/Qwen2.5-7B-Instruct"
client = InferenceClient(token=HF_API_KEY) if HF_API_KEY else None

# Initialize Azure Blob Storage client
s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_DEFAULT_REGION,
)

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
    ssl_ca = os.getenv("ssl_ca")
    return pymysql.connect(
        host = os.getenv("hostname"),
        port = int(os.getenv("PORT", 3306)),
        user = os.getenv("Clouduser"),            # must be username@servername
        password = os.getenv("passwordazure"),
        database = os.getenv("DB_NAME"),
        ssl_ca = os.getenv("ssl_ca"),
        ssl={'ca': ssl_ca},      # Azure requires SSL
        charset='utf8mb4'
    )



# ---- Load location/property types ----
locations = []
propertyTypes = []


def load_location_and_property_types():
    global locations, propertyTypes
    try:
        conn = get_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
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


# ---- Helper function to update RAG index ----
def update_rag_index(property_data: dict):
    """Add a new property to the RAG index"""
    global collections, chroma_client, embmodel
    
    if not chroma_client:
        chroma_client = chromadb.PersistentClient(path="./chroma_joined_index")
    
    try:
        # Try to get existing collection
        try:
            collections = chroma_client.get_collection("property_hub_index")
        except:
            try:
                collections = chroma_client.get_collection("zameen_joined_index")
            except:
                # Create new collection if it doesn't exist
                collections = chroma_client.create_collection(
                    name="property_hub_index",
                    embedding_function=None
                )
    except Exception as e:
        print(f"Error accessing collection: {e}")
        return False
    
    try:
        # Create document from property data
        doc = (
            f"Property ID {property_data.get('id', 'new')} is a {property_data.get('prop_type', 'Property')} "
            f"for {property_data.get('purpose', 'sale')} in {property_data.get('location', 'Unknown')}. "
            f"It has {property_data.get('beds', 0)} beds, {property_data.get('baths', 0)} baths, "
            f"covered area {property_data.get('covered_area', 0)} sqft, priced at {property_data.get('price', 0)}. "
            f"Amenities include: {property_data.get('amenities', 'N/A')}."
        )
        
        # Generate embedding
        emb = embmodel.encode([doc])[0].tolist()
        
        # Add to collection
        property_id = property_data.get('id', f"property_{int(np.random.random() * 1000000)}")
        collections.add(
            ids=[f"property_{property_id}"],
            documents=[doc],
            embeddings=[emb],
            metadatas=[{"type": "property", "location": property_data.get('location', 'Unknown')}]
        )
        
        print(f"✅ Added property {property_id} to RAG index")
        return True
    except Exception as e:
        print(f"❌ Error updating RAG index: {e}")
        return False

# ---- Routes ----
@app.get("/")
def home():
    return {"message": "Property Hub API is running"}


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
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    query = """
        SELECT id, prop_type, purpose, covered_area, price, location, beds, baths, amenities
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
   
    return {"locations": locations}


@app.get("/prop_type")
def get_prop_type(purpose: str = "sale"):
    
    return {"prop_type": propertyTypes}


@app.get("/listings/{property_id}")
def get_property_by_id(property_id: int):
    """Get a single property by ID"""
    conn = get_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    query = """
        SELECT id, prop_type, purpose, covered_area, price, location, beds, baths, amenities
        FROM property_data
        WHERE id = %s
    """
    cursor.execute(query, (property_id,))
    data = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not data:
        raise HTTPException(status_code=404, detail="Property not found")
    
    return data


class ComparisonRequest(BaseModel):
    property_id_1: int
    property_id_2: int
    question: str = "Compare these two properties in detail."


@app.post("/compare")
def compare_properties(req: ComparisonRequest):
    """Compare two properties using the chatbot"""
    import logging
    logger = logging.getLogger(__name__)
    
    # Log incoming request
    print(f"[/compare] 📨 Received compare request: property_id_1={req.property_id_1}, property_id_2={req.property_id_2}, question={req.question[:100]}...")
    logger.info(f"Compare request: property_id_1={req.property_id_1}, property_id_2={req.property_id_2}")
    
    try:
        conn = get_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # Get both properties
        query = """
            SELECT id, prop_type, purpose, covered_area, price, location, beds, baths, amenities
            FROM property_data
            WHERE id IN (%s, %s)
        """
        cursor.execute(query, (req.property_id_1, req.property_id_2))
        properties = cursor.fetchall()
        cursor.close()
        conn.close()
        
        print(f"[/compare] 🔍 Found {len(properties)} properties in database")
        logger.info(f"Found {len(properties)} properties for comparison")
        
        if len(properties) != 2:
            print(f"[/compare] ❌ Properties not found: expected 2, got {len(properties)}")
            logger.warning(f"Properties not found: expected 2, got {len(properties)}")
            raise HTTPException(status_code=404, detail="One or both properties not found")
        
        prop1 = properties[0] if properties[0]['id'] == req.property_id_1 else properties[1]
        prop2 = properties[1] if properties[0]['id'] == req.property_id_1 else properties[0]
        
        print(f"[/compare] ✅ Property 1: {prop1['prop_type']} in {prop1['location']} - PKR {prop1['price']:,.0f}")
        print(f"[/compare] ✅ Property 2: {prop2['prop_type']} in {prop2['location']} - PKR {prop2['price']:,.0f}")
        
        # Build comparison prompt
        comparison_context = f"""
PROPERTY 1 (ID: {prop1['id']}):
- Type: {prop1['prop_type']}
- Purpose: {prop1['purpose']}
- Location: {prop1['location']}
- Price: PKR {prop1['price']:,.0f}
- Covered Area: {prop1['covered_area']} sqft
- Bedrooms: {prop1['beds']}
- Bathrooms: {prop1['baths']}
- Amenities: {prop1.get('amenities', 'N/A')}

PROPERTY 2 (ID: {prop2['id']}):
- Type: {prop2['prop_type']}
- Purpose: {prop2['purpose']}
- Location: {prop2['location']}
- Price: PKR {prop2['price']:,.0f}
- Covered Area: {prop2['covered_area']} sqft
- Bedrooms: {prop2['beds']}
- Bathrooms: {prop2['baths']}
- Amenities: {prop2.get('amenities', 'N/A')}
"""
        
        comparison_prompt = f"""You are Property Hub's intelligent property assistant. Compare these two properties in detail.

{comparison_context}

USER QUESTION: {req.question}

Provide a comprehensive comparison that includes:
1. Price comparison and value analysis
2. Size and space comparison
3. Location advantages/disadvantages
4. Feature comparison (beds, baths, amenities)
5. Price per square foot comparison
6. Overall recommendation based on the user's question

Be specific with numbers and calculations. Format your response clearly with paragraphs and bullet points."""
        
        print(f"[/compare] 🤖 Calling chatbot to generate comparison (prompt length: {len(comparison_prompt)} chars)")
        logger.info(f"Generating comparison with prompt length: {len(comparison_prompt)}")
        
        # Use chatbot to generate comparison
        result = callWrapper(comparison_prompt)
        
        comparison_text = result.get("response", "Unable to generate comparison.")
        print(f"[/compare] ✅ Comparison generated (length: {len(comparison_text)} chars)")
        logger.info(f"Comparison generated successfully, length: {len(comparison_text)}")
        
        return {
            "property1": prop1,
            "property2": prop2,
            "comparison": comparison_text,
            "question": req.question
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print(f"[/compare] ❌ Error in compare endpoint: {str(e)}")
        print(f"[/compare] 📋 Traceback:\n{error_traceback}")
        logger.error(f"Error in compare endpoint: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating comparison: {str(e)}")


# ---- Add Listing Schema ----
class AddListingInput(BaseModel):
    prop_type: str
    purpose: str
    covered_area: float
    price: float
    location: str
    beds: int
    baths: int
    amenities: str = ""


@app.post("/listings/add")
async def add_listing(input_data: AddListingInput):
    """Add a new property listing and update RAG index"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(  pymysql.cursors.DictCursor)
        
        # Insert into database
        insert_query = """
            INSERT INTO property_data (prop_type, purpose, covered_area, price, location, beds, baths, amenities)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(
            insert_query,
            (
                input_data.prop_type,
                input_data.purpose,
                input_data.covered_area,
                input_data.price,
                input_data.location,
                input_data.beds,
                input_data.baths,
                input_data.amenities,
            )
        )
        
        # Get the inserted ID
        property_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        
        # Update RAG index
        property_data = {
            "id": property_id,
            "prop_type": input_data.prop_type,
            "purpose": input_data.purpose,
            "covered_area": input_data.covered_area,
            "price": input_data.price,
            "location": input_data.location,
            "beds": input_data.beds,
            "baths": input_data.baths,
            "amenities": input_data.amenities,
        }
        update_rag_index(property_data)
        
        return {
            "success": True,
            "message": "Listing added successfully",
            "id": property_id
        }
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to add listing: {str(e)}")
    finally:
        if conn:
            conn.close()


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


def build_comparison_insights(bundles: List[dict]) -> str:
    """Produce textual insights (cheapest, best value, etc.) for prompt guidance."""
    if not bundles:
        return "Not enough structured data for comparison."

    insights = []
    priced_props = []
    areas_props = []
    value_props = []

    for bundle in bundles:
        data = bundle.get("data") or {}
        price = data.get("price")
        area = data.get("area")
        prop_type = data.get("prop_type") or "Property"
        location = data.get("location") or "Unknown"
        
        if isinstance(price, (int, float)):
            priced_props.append({"price": price, "type": prop_type, "location": location})
        if isinstance(area, (int, float)):
            areas_props.append({"area": area, "type": prop_type, "location": location})
        if isinstance(price, (int, float)) and isinstance(area, (int, float)) and area > 0:
            price_per_area = price / area
            value_props.append({"price_per_area": price_per_area, "type": prop_type, "location": location, "price": price, "area": area})

    if priced_props:
        cheapest = min(priced_props, key=lambda x: x["price"])
        insights.append(
            f"Cheapest option: {cheapest['type']} in {cheapest['location']} at PKR {cheapest['price']:,.0f}"
        )
    if priced_props:
        premium = max(priced_props, key=lambda x: x["price"])
        insights.append(
            f"Highest budget option: {premium['type']} in {premium['location']} at PKR {premium['price']:,.0f}"
        )
    if areas_props:
        largest = max(areas_props, key=lambda x: x["area"])
        insights.append(
            f"Largest covered area: {largest['type']} in {largest['location']} with {largest['area']} sqft"
        )
    if value_props:
        best_value = min(value_props, key=lambda x: x["price_per_area"])
        insights.append(
            f"Best price/area: {best_value['type']} in {best_value['location']} at PKR {best_value['price_per_area']:,.0f} per sqft"
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
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # 1. Get last user message
        last_user = messages[-1].content
        print(f"[generate_chat_response] 📨 Processing chat request with {len(messages)} messages")
        print(f"[generate_chat_response] 💬 Last user message: {last_user[:100]}...")
        logger.info(f"generate_chat_response called with {len(messages)} messages")

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
        print(f"[generate_chat_response] 🔄 Rewriting query...")
        rewrite_result = callWrapper(rewrite_prompt)
        if "Input Guardrail Violation" in rewrite_result["response"] or "Output Guardrail Violation" in rewrite_result["response"]:
            print(f"[generate_chat_response] ❌ Guardrail violation in query rewrite")
            return {"text": rewrite_result["response"], "properties": []}
        rewritten_query = rewrite_result["response"] if rewrite_result["response"] else last_user
        print(f"[generate_chat_response] ✅ Rewritten query: {rewritten_query[:100]}...")

        # 5. Enhanced RAG Retrieval
        print(f"[generate_chat_response] 🔍 Retrieving RAG results...")
        rag_results = retrieve(rewritten_query, n_results=20, top_k=7)
        context_docs = rag_results["documents"]
        context_scores = rag_results["scores"]
        context_metas = rag_results.get("metadatas", []) or []
        print(f"[generate_chat_response] ✅ Retrieved {len(context_docs)} documents from RAG")

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

        comparison_summary = build_comparison_insights(bundled_results)

        # 6. Determine if context is useful
        avg_score = np.mean(context_scores) if context_scores else 0.0
        use_context = avg_score > 0.25  # Lower threshold for better coverage

        # 7. Enhanced LLM prompt with reasoning, mathematical capabilities, and sentiment awareness
        sentiment_context = "\n".join(sentiment_info) if sentiment_info else "No specific sentiment data found in retrieved documents."

        main_prompt = f"""You are Property Hub's intelligent property assistant. You are conversational, helpful, and have strong reasoning abilities.

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
        print(f"[generate_chat_response] 🤖 Generating final answer (prompt length: {len(main_prompt)} chars)...")
        answer_result = callWrapper(main_prompt)
        if "Input Guardrail Violation" in answer_result["response"] or "Output Guardrail Violation" in answer_result["response"]:
            print(f"[generate_chat_response] ❌ Guardrail violation in final answer")
            return {"text": answer_result["response"], "properties": []}
        generated = answer_result["response"] if answer_result["response"] else "Sorry, no response generated."
        print(f"[generate_chat_response] ✅ Generated answer (length: {len(generated)} chars)")

        # Final duplicate check
        recent_assistant = [m.content for m in reversed(messages) if m.role == "assistant"]
        if recent_assistant and recent_assistant[0].strip() == generated.strip():
            generated = "I've already provided that information. Would you like me to expand on a specific aspect or help with something else?"

        # Don't send cards - just use comparison data for better text responses
        return {"text": generated, "properties": []}

    except Exception as e:
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        
        error_type = type(e).__name__
        error_message = str(e)
        error_traceback = traceback.format_exc()
        
        print(f"[generate_chat_response] ❌ Chat Error: {error_type}: {error_message}")
        print(f"[generate_chat_response] 📋 Traceback:\n{error_traceback}")
        logger.error(f"Error in generate_chat_response: {error_type}: {error_message}", exc_info=True)
        
        return {
            "text": f"Sorry, I encountered an error. Please try again. Error: {error_message}",
            "properties": [],
        }




def callWrapper(prompt: str):
    import logging
    import traceback
    logger = logging.getLogger(__name__)

    prompt_length = len(prompt)
    prompt_preview = prompt[:200] + "..." if len(prompt) > 200 else prompt
    print(f"[callWrapper] 📝 Prompt length: {prompt_length} chars, preview: {prompt_preview[:100]}...")
    logger.info(f"callWrapper called with prompt length: {prompt_length}")

    promptpass = policy_engine.validate_input(prompt)
    if not promptpass['passed']:
        print(f"[callWrapper] ❌ Input Guardrail Violation: {promptpass['reason']}")
        logger.warning(f"Input guardrail violation: {promptpass['reason']}")
        return {
            "response": f"Input Guardrail Violation: {promptpass['reason']}",
            "properties": [],
        }

    if not client:
        print("[callWrapper] ❌ Hugging Face API client not configured")
        logger.error("Hugging Face API client not configured. HF_API_KEY not set.")
        return {
            "response": "Hugging Face API client not configured. Please set HF_API_KEY.",
            "properties": [],
        }

    try:
        print(f"[callWrapper] 🔄 Calling Hugging Face InferenceClient chat.completions.create: {HF_MODEL}")
        logger.info(f"Calling Hugging Face InferenceClient chat.completions.create: {HF_MODEL}")
        completion = client.chat.completions.create(
            model=HF_MODEL,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )
        response_text = completion.choices[0].message.content.strip() if completion and completion.choices and completion.choices[0].message and completion.choices[0].message.content else ""

        outputpass = policy_engine.moderate_output(response_text)
        if not outputpass['passed']:
            print(f"[callWrapper] ❌ Output Guardrail Violation: {outputpass['reason']}")
            logger.warning(f"Output guardrail violation: {outputpass['reason']}")
            return {
                "response": f"Output Guardrail Violation: {outputpass['reason']}",
                "properties": [],
            }

        print(f"[callWrapper] ✅ Successfully generated response (length: {len(response_text)} chars)")
        logger.info(f"Successfully generated response, length: {len(response_text)}")
        return {
            "response": response_text,
            "properties": [],
        }
    except Exception as e:
        error_type = type(e).__name__
        error_message = str(e)
        error_traceback = traceback.format_exc()
        print(f"[callWrapper] ❌ Exception occurred: {error_type}: {error_message}")
        print(f"[callWrapper] 📋 Full traceback:\n{error_traceback}")
        logger.error(f"Error in callWrapper: {error_type}: {error_message}", exc_info=True)
        return {
            "response": f"Error generating response: {error_type}: {error_message}",
            "properties": [],
        }


@app.post("/chat")
def chat(req: ChatRequest):
    """Chat endpoint - returns a SINGLE high-quality text response per request."""
    import logging
    logger = logging.getLogger(__name__)
    
    # Log incoming request
    num_messages = len(req.messages)
    last_user_message = req.messages[-1].content if req.messages else "No messages"
    print(f"[/chat] 📨 Received chat request with {num_messages} messages")
    print(f"[/chat] 📝 Last user message: {last_user_message[:100]}...")
    logger.info(f"Chat request received: {num_messages} messages, last message preview: {last_user_message[:100]}")
    
    try:
        payload = generate_chat_response(req.messages)
        response_text = payload.get("text", "")
        
        print(f"[/chat] ✅ Generated response (length: {len(response_text)} chars)")
        logger.info(f"Chat response generated successfully, length: {len(response_text)}")
        
        return {
            "response": response_text,
          # No cards - all info in text response
        }
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print(f"[/chat] ❌ Error in chat endpoint: {str(e)}")
        print(f"[/chat] 📋 Traceback:\n{error_traceback}")
        logger.error(f"Error in chat endpoint: {str(e)}", exc_info=True)
        
        return {
            "response": f"An error occurred while processing your request: {str(e)}",
        }
class UpdateListingInput(BaseModel):
    prop_type: str
    purpose: str
    covered_area: float
    price: float
    location: str
    beds: int
    baths: int
    amenities: str = ""

@app.put("/listings/{property_id}/update")
def update_listing(
    property_id: int = Path(..., description="Property ID to update"),
    input_data: UpdateListingInput = Body(...)
):
    """Update a property listing by ID"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        update_query = """
            UPDATE property_data
            SET prop_type=%s, purpose=%s, covered_area=%s, price=%s, location=%s, beds=%s, baths=%s, amenities=%s
            WHERE id=%s
        """
        cursor.execute(
            update_query,
            (
                input_data.prop_type,
                input_data.purpose,
                input_data.covered_area,
                input_data.price,
                input_data.location,
                input_data.beds,
                input_data.baths,
                input_data.amenities,
                property_id,
            )
        )
        conn.commit()
        cursor.close()
        # Optionally update RAG index here if needed
        return {"success": True, "message": "Listing updated successfully"}
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update listing: {str(e)}")
    finally:
        if conn:
            conn.close()

# ---- Delete Listing Endpoint ----
@app.delete("/listings/{property_id}/delete")
def delete_listing(property_id: int = Path(..., description="Property ID to delete")):
    """Delete a property listing by ID"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        delete_query = "DELETE FROM property_data WHERE id=%s"
        cursor.execute(delete_query, (property_id,))
        conn.commit()
        cursor.close()
        # Optionally update RAG index here if needed
        return {"success": True, "message": "Listing deleted successfully"}
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete listing: {str(e)}")
    finally:
        if conn:
            conn.close()
