# api/vectorstore_router.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import sys
import os
import yaml
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
import torch
from transaksional.app.config import settings
router = APIRouter(prefix=f"{settings.informational_prefix}/vectorstore", tags=["Vectorstore"])



# ==============================
# Setup project root
# ==============================
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

# ==============================
# Load .env
# ==============================
load_dotenv()

# ==============================
# Load config.yaml
# ==============================
config_path = os.path.join(ROOT_DIR, "config", "config.yaml")
with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# ==============================
# Helper: resolve env vars
# ==============================
def resolve_env_vars(d):
    if isinstance(d, dict):
        return {k: resolve_env_vars(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [resolve_env_vars(v) for v in d]
    elif isinstance(d, str) and d.startswith("${") and d.endswith("}"):
        return os.getenv(d[2:-1], "")
    else:
        return d

config = resolve_env_vars(config)

# ==============================
# Setup embeddings
# ==============================
embedding_cfg = config["embeddings"]
if embedding_cfg["model"] == "openai":
    model_name = embedding_cfg["openai"]["model_name"]
    embeddings = OpenAIEmbeddings(
        model=model_name,
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )
elif embedding_cfg["model"] == "huggingface":
    model_name = embedding_cfg["huggingface"]["model_name"]
    device = embedding_cfg["huggingface"].get("device", "cpu")
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"  # fallback jika CUDA tidak tersedia
    embeddings = HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": device},
        encode_kwargs={"normalize_embeddings": True}
    )
else:
    raise NotImplementedError(f"Model embeddings {embedding_cfg['model']} belum didukung.")

# ==============================
# Setup ChromaDB
# ==============================
chroma_cfg = config["vectordb"]["chroma"]
collection_metadata = {"hnsw:space": chroma_cfg.get("distance_function", "cosine")}
vectorstore = Chroma(
    collection_name=chroma_cfg["collection_name"],
    embedding_function=embeddings,
    persist_directory=chroma_cfg["persist_directory"],
    collection_metadata=collection_metadata
)

# ==============================
# Endpoint: Get all documents
# ==============================
@router.get("/", summary="Get all documents from vectorstore")
def get_documents():
    try:
        docs = vectorstore._collection.get(include=["documents", "metadatas"])
        results = []
        for idx, (content, metadata) in enumerate(zip(docs["documents"], docs["metadatas"])):
            results.append({
                "content": content,
                "metadata": metadata,
            })
        return {"status_code": 200, "message": f"{len(results)} documents retrieved", "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

