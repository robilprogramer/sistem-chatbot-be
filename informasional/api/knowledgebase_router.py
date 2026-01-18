
"""
Knowledge Base Router - API untuk melihat isi VectorDB

ENDPOINTS:
- GET  /kb/stats                    : Statistics overview
- GET  /kb/documents                : List all documents
- GET  /kb/documents/{doc_id}       : Get document detail dengan semua chunks
- GET  /kb/documents/{doc_id}/full  : Get full reconstructed document
- GET  /kb/search                   : Search documents by metadata
- GET  /kb/chunks                   : List chunks dengan pagination
- GET  /kb/chunks/{chunk_id}        : Get chunk detail
- DELETE /kb/documents/{doc_id}     : Delete document dari vectorstore
- GET  /kb/export                   : Export all documents metadata
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from collections import defaultdict

from informasional.utils.vectorstore_utils import get_vectorstore
from informasional.utils.embedding_utils import get_embedding_manager
from transaksional.app.config import settings


# ============================================================================
# ROUTER SETUP
# ============================================================================
router = APIRouter(
    prefix=f"{settings.informational_prefix}/kb",
    tags=["Knowledge Base"]
)

# Config path
CONFIG_PATH = "informasional/config/config.yaml"


# ============================================================================
# SCHEMAS
# ============================================================================
class DocumentSummary(BaseModel):
    """Document summary schema"""
    document_id: str
    source: str
    jenjang: str = ""
    cabang: str = ""
    tahun: str = ""
    category: str = ""
    total_chunks: int
    total_length: int


class ChunkSummary(BaseModel):
    """Chunk summary schema"""
    chunk_id: str
    document_id: str
    chunk_index: int
    total_chunks: int
    content_length: int
    content_preview: str


class DocumentDetail(BaseModel):
    """Document detail with chunks"""
    document_id: str
    source: str
    metadata: Dict[str, Any]
    total_chunks: int
    total_length: int
    chunks: List[Dict[str, Any]]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================
def get_all_documents_from_vectorstore() -> Dict[str, List[Dict]]:
    """
    Get all documents from vectorstore, grouped by document_id
    """
    vectorstore_manager = get_vectorstore(CONFIG_PATH)
    collection = vectorstore_manager.collection
    
    # Get all data
    try:
        results = collection.get(
            include=["documents", "metadatas"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error accessing vectorstore: {e}")
    
    if not results['ids']:
        return {}
    
    # Group by document_id
    docs_by_id = defaultdict(list)
    
    for chunk_id, content, metadata in zip(
        results['ids'],
        results['documents'],
        results['metadatas']
    ):
        doc_id = metadata.get('document_id', 'unknown')
        docs_by_id[doc_id].append({
            'chunk_id': chunk_id,
            'content': content,
            'metadata': metadata,
            'chunk_index': metadata.get('chunk_index', 0)
        })
    
    # Sort chunks by chunk_index
    for doc_id in docs_by_id:
        docs_by_id[doc_id].sort(key=lambda x: x['chunk_index'])
    
    return dict(docs_by_id)


# ============================================================================
# API: Statistics Overview
# ============================================================================
@router.get("/stats")
async def get_knowledgebase_stats():
    """
    Get Knowledge Base statistics
    
    Returns:
        - total_vectors: Total chunks in vectorstore
        - total_documents: Unique documents
        - by_jenjang: Distribution by jenjang
        - by_cabang: Distribution by cabang
        - by_category: Distribution by category
        - embedding_info: Current embedding configuration
    """
    vectorstore_manager = get_vectorstore(CONFIG_PATH)
    embedding_manager = get_embedding_manager(CONFIG_PATH)
    
    # Get all documents
    docs_by_id = get_all_documents_from_vectorstore()
    
    # Calculate stats
    total_vectors = sum(len(chunks) for chunks in docs_by_id.values())
    total_documents = len(docs_by_id)
    
    # Distribution stats
    jenjang_dist = defaultdict(int)
    cabang_dist = defaultdict(int)
    category_dist = defaultdict(int)
    tahun_dist = defaultdict(int)
    
    for doc_id, chunks in docs_by_id.items():
        if chunks:
            meta = chunks[0]['metadata']
            jenjang = meta.get('jenjang', 'Unknown') or 'Unknown'
            cabang = meta.get('cabang', 'Unknown') or 'Unknown'
            category = meta.get('category', meta.get('kategori', 'Unknown')) or 'Unknown'
            tahun = meta.get('tahun', 'Unknown') or 'Unknown'
            
            jenjang_dist[jenjang] += 1
            cabang_dist[cabang] += 1
            category_dist[category] += 1
            tahun_dist[tahun] += 1
    
    # Calculate average chunks per document
    avg_chunks = total_vectors / total_documents if total_documents > 0 else 0
    
    return {
        "status": "ok",
        "statistics": {
            "total_vectors": total_vectors,
            "total_documents": total_documents,
            "avg_chunks_per_document": round(avg_chunks, 2)
        },
        "distribution": {
            "by_jenjang": dict(jenjang_dist),
            "by_cabang": dict(cabang_dist),
            "by_category": dict(category_dist),
            "by_tahun": dict(tahun_dist)
        },
        "embedding_info": embedding_manager.get_info(),
        "vectorstore_info": {
            "collection_name": vectorstore_manager.collection.name,
            "distance_function": vectorstore_manager.collection.metadata.get("hnsw:space", "unknown")
        }
    }


# ============================================================================
# API: List All Documents
# ============================================================================
@router.get("/documents")
async def list_documents(
    jenjang: Optional[str] = Query(default=None, description="Filter by jenjang: TK, SD, SMP, SMA"),
    cabang: Optional[str] = Query(default=None, description="Filter by cabang"),
    tahun: Optional[str] = Query(default=None, description="Filter by tahun"),
    category: Optional[str] = Query(default=None, description="Filter by category"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200)
):
    """
    List all documents in Knowledge Base
    
    Returns list of documents with summary info
    """
    docs_by_id = get_all_documents_from_vectorstore()
    
    # Build document summaries
    documents = []
    
    for doc_id, chunks in docs_by_id.items():
        if not chunks:
            continue
        
        # Get metadata from first chunk
        meta = chunks[0]['metadata']
        
        doc_jenjang = meta.get('jenjang', '') or ''
        doc_cabang = meta.get('cabang', '') or ''
        doc_tahun = meta.get('tahun', '') or ''
        doc_category = meta.get('category', meta.get('kategori', '')) or ''
        
        # Apply filters
        if jenjang and doc_jenjang.lower() != jenjang.lower():
            continue
        if cabang and cabang.lower() not in doc_cabang.lower():
            continue
        if tahun and tahun not in doc_tahun:
            continue
        if category and category.lower() not in doc_category.lower():
            continue
        
        # Calculate total length
        total_length = sum(len(c['content']) for c in chunks)
        
        documents.append({
            "document_id": doc_id,
            "source": meta.get('source', meta.get('filename', 'Unknown')),
            "jenjang": doc_jenjang,
            "cabang": doc_cabang,
            "tahun": doc_tahun,
            "category": doc_category,
            "total_chunks": len(chunks),
            "total_length": total_length
        })
    
    # Sort by source name
    documents.sort(key=lambda x: x['source'])
    
    # Apply pagination
    total = len(documents)
    documents = documents[skip:skip + limit]
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "filters_applied": {
            "jenjang": jenjang,
            "cabang": cabang,
            "tahun": tahun,
            "category": category
        },
        "documents": documents
    }


# ============================================================================
# API: Get Document Detail
# ============================================================================
@router.get("/documents/{document_id}")
async def get_document_detail(document_id: str):
    """
    Get document detail dengan semua chunks
    
    Returns:
        - document_id
        - source
        - metadata
        - total_chunks
        - chunks (with content preview)
    """
    vectorstore_manager = get_vectorstore(CONFIG_PATH)
    
    # Get chunks for this document
    chunks_data = vectorstore_manager.get_by_document_id(document_id)
    
    if not chunks_data:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {document_id}"
        )
    
    # Build response
    first_chunk = chunks_data[0]
    metadata = first_chunk['metadata']
    
    total_length = sum(len(c['content']) for c in chunks_data)
    
    return {
        "document_id": document_id,
        "source": metadata.get('source', metadata.get('filename', 'Unknown')),
        "metadata": {
            "jenjang": metadata.get('jenjang', ''),
            "cabang": metadata.get('cabang', ''),
            "tahun": metadata.get('tahun', ''),
            "category": metadata.get('category', metadata.get('kategori', '')),
            "total_pages": metadata.get('total_pages', ''),
            "extraction_method": metadata.get('extraction_method', '')
        },
        "total_chunks": len(chunks_data),
        "total_length": total_length,
        "chunks": [
            {
                "chunk_index": c['chunk_index'],
                "chunk_id": c['chroma_id'],
                "content_length": len(c['content']),
                "content_preview": c['content'][:300] + "..." if len(c['content']) > 300 else c['content']
            }
            for c in chunks_data
        ]
    }


# ============================================================================
# API: Get Full Reconstructed Document
# ============================================================================
@router.get("/documents/{document_id}/full")
async def get_full_document(document_id: str):
    """
    Get full reconstructed document (semua chunks digabung)
    
    Useful untuk:
    - Preview dokumen lengkap
    - Debug content extraction
    - Export content
    """
    vectorstore_manager = get_vectorstore(CONFIG_PATH)
    
    # Get chunks
    chunks_data = vectorstore_manager.get_by_document_id(document_id)
    
    if not chunks_data:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {document_id}"
        )
    
    # Reconstruct document
    full_content = "\n\n".join([c['content'] for c in chunks_data])
    
    metadata = chunks_data[0]['metadata']
    
    return {
        "document_id": document_id,
        "source": metadata.get('source', 'Unknown'),
        "metadata": {
            "jenjang": metadata.get('jenjang', ''),
            "cabang": metadata.get('cabang', ''),
            "tahun": metadata.get('tahun', ''),
            "category": metadata.get('category', '')
        },
        "total_chunks": len(chunks_data),
        "total_length": len(full_content),
        "content": full_content
    }


# ============================================================================
# API: Search Documents by Metadata
# ============================================================================
@router.get("/search")
async def search_documents(
    q: str = Query(..., min_length=1, description="Search query"),
    jenjang: Optional[str] = None,
    cabang: Optional[str] = None,
    tahun: Optional[str] = None,
    top_k: int = Query(default=10, ge=1, le=50)
):
    """
    Search documents by content similarity
    
    Returns similar documents with relevance scores
    """
    vectorstore_manager = get_vectorstore(CONFIG_PATH)
    
    # Build filter
    filter_dict = {}
    if jenjang:
        filter_dict['jenjang'] = jenjang
    if cabang:
        filter_dict['cabang'] = cabang
    if tahun:
        filter_dict['tahun'] = tahun
    
    # Search
    results = vectorstore_manager.similarity_search_with_score(
        query=q,
        k=top_k,
        filter=filter_dict if filter_dict else None
    )
    
    # Group by document_id and get max score
    docs_scores = {}
    docs_previews = {}
    
    for doc, score in results:
        doc_id = doc.metadata.get('document_id', 'unknown')
        similarity = 1 - (score / 2)  # Convert distance to similarity
        
        if doc_id not in docs_scores or similarity > docs_scores[doc_id]:
            docs_scores[doc_id] = similarity
            docs_previews[doc_id] = {
                'source': doc.metadata.get('source', 'Unknown'),
                'jenjang': doc.metadata.get('jenjang', ''),
                'cabang': doc.metadata.get('cabang', ''),
                'tahun': doc.metadata.get('tahun', ''),
                'preview': doc.page_content[:200] + "..."
            }
    
    # Sort by score
    sorted_docs = sorted(
        docs_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    return {
        "query": q,
        "filters": filter_dict,
        "total_results": len(sorted_docs),
        "results": [
            {
                "document_id": doc_id,
                "similarity": round(score, 4),
                **docs_previews[doc_id]
            }
            for doc_id, score in sorted_docs
        ]
    }


# ============================================================================
# API: List Chunks with Pagination
# ============================================================================
@router.get("/chunks")
async def list_chunks(
    document_id: Optional[str] = Query(default=None, description="Filter by document_id"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200)
):
    """
    List all chunks dengan pagination
    """
    vectorstore_manager = get_vectorstore(CONFIG_PATH)
    collection = vectorstore_manager.collection
    
    # Get chunks
    try:
        if document_id:
            results = collection.get(
                where={"document_id": document_id},
                include=["documents", "metadatas"]
            )
        else:
            results = collection.get(
                include=["documents", "metadatas"]
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    if not results['ids']:
        return {
            "total": 0,
            "skip": skip,
            "limit": limit,
            "chunks": []
        }
    
    # Build chunks list
    chunks = []
    for chunk_id, content, metadata in zip(
        results['ids'],
        results['documents'],
        results['metadatas']
    ):
        chunks.append({
            "chunk_id": chunk_id,
            "document_id": metadata.get('document_id', 'unknown'),
            "source": metadata.get('source', 'Unknown'),
            "chunk_index": metadata.get('chunk_index', 0),
            "total_chunks": metadata.get('total_chunks', 1),
            "content_length": len(content),
            "content_preview": content[:150] + "..." if len(content) > 150 else content
        })
    
    # Sort by document_id then chunk_index
    chunks.sort(key=lambda x: (x['document_id'], x['chunk_index']))
    
    # Pagination
    total = len(chunks)
    chunks = chunks[skip:skip + limit]
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "chunks": chunks
    }


# ============================================================================
# API: Get Chunk Detail
# ============================================================================
@router.get("/chunks/{chunk_id}")
async def get_chunk_detail(chunk_id: str):
    """
    Get single chunk detail with full content
    """
    vectorstore_manager = get_vectorstore(CONFIG_PATH)
    collection = vectorstore_manager.collection
    
    try:
        results = collection.get(
            ids=[chunk_id],
            include=["documents", "metadatas"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    if not results['ids']:
        raise HTTPException(
            status_code=404,
            detail=f"Chunk not found: {chunk_id}"
        )
    
    content = results['documents'][0]
    metadata = results['metadatas'][0]
    
    return {
        "chunk_id": chunk_id,
        "document_id": metadata.get('document_id', 'unknown'),
        "source": metadata.get('source', 'Unknown'),
        "chunk_index": metadata.get('chunk_index', 0),
        "total_chunks": metadata.get('total_chunks', 1),
        "content_length": len(content),
        "content": content,
        "metadata": metadata
    }


# ============================================================================
# API: Delete Document from VectorStore
# ============================================================================
@router.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """
    Delete document dari vectorstore
    
    WARNING: Ini akan menghapus semua chunks untuk document_id ini dari ChromaDB.
    Data di PostgreSQL tidak terpengaruh.
    """
    vectorstore_manager = get_vectorstore(CONFIG_PATH)
    
    # Check if document exists
    chunks_data = vectorstore_manager.get_by_document_id(document_id)
    
    if not chunks_data:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {document_id}"
        )
    
    # Delete
    deleted_count = vectorstore_manager.delete_by_filter({"document_id": document_id})
    
    return {
        "status": "ok",
        "message": f"Document deleted from vectorstore",
        "document_id": document_id,
        "chunks_deleted": deleted_count
    }


# ============================================================================
# API: Export All Documents Metadata
# ============================================================================
@router.get("/export")
async def export_documents_metadata():
    """
    Export all documents metadata (tanpa content)
    
    Useful untuk:
    - Backup metadata
    - Analysis
    - Reporting
    """
    docs_by_id = get_all_documents_from_vectorstore()
    
    export_data = []
    
    for doc_id, chunks in docs_by_id.items():
        if not chunks:
            continue
        
        meta = chunks[0]['metadata']
        total_length = sum(len(c['content']) for c in chunks)
        
        export_data.append({
            "document_id": doc_id,
            "source": meta.get('source', 'Unknown'),
            "jenjang": meta.get('jenjang', ''),
            "cabang": meta.get('cabang', ''),
            "tahun": meta.get('tahun', ''),
            "category": meta.get('category', ''),
            "total_chunks": len(chunks),
            "total_length": total_length,
            "chunk_ids": [c['chunk_id'] for c in chunks]
        })
    
    return {
        "total_documents": len(export_data),
        "exported_at": __import__('datetime').datetime.now().isoformat(),
        "documents": export_data
    }


# ============================================================================
# API: Get Unique Values for Filters
# ============================================================================
@router.get("/filters")
async def get_available_filters():
    """
    Get available filter values
    
    Returns unique values untuk:
    - jenjang
    - cabang
    - tahun
    - category
    """
    docs_by_id = get_all_documents_from_vectorstore()
    
    jenjang_set = set()
    cabang_set = set()
    tahun_set = set()
    category_set = set()
    
    for doc_id, chunks in docs_by_id.items():
        if chunks:
            meta = chunks[0]['metadata']
            
            if meta.get('jenjang'):
                jenjang_set.add(meta['jenjang'])
            if meta.get('cabang'):
                cabang_set.add(meta['cabang'])
            if meta.get('tahun'):
                tahun_set.add(meta['tahun'])
            if meta.get('category') or meta.get('kategori'):
                category_set.add(meta.get('category') or meta.get('kategori'))
    
    return {
        "jenjang": sorted(list(jenjang_set)),
        "cabang": sorted(list(cabang_set)),
        "tahun": sorted(list(tahun_set)),
        "category": sorted(list(category_set))
    }