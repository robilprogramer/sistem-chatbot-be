# 🔍 Enhanced RAG dengan Document Aggregation

## Solusi untuk Masalah "Informasi Terpotong"

Dokumentasi ini menjelaskan solusi untuk masalah chunks yang terpotong saat retrieval, sehingga context yang diberikan ke LLM menjadi lengkap.

---

## 📊 Diagram Alur

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           INGESTION PIPELINE                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Document          Enhanced Chunker              ChromaDB                    │
│  ┌──────────┐      ┌────────────────────┐       ┌──────────────────┐        │
│  │ content  │      │ 1. Generate        │       │ Store dengan     │        │
│  │ metadata │ ──▶  │    document_id     │  ──▶  │ document_id      │        │
│  │          │      │    (KONSISTEN)     │       │ di metadata      │        │
│  └──────────┘      │                    │       └──────────────────┘        │
│                    │ 2. Split ke chunks │                                    │
│                    │    dengan:         │       Setiap chunk punya:          │
│                    │    - chunk_index   │       ✓ document_id (sama)         │
│                    │    - chunk_id      │       ✓ chunk_index (urutan)       │
│                    │    - prev/next     │       ✓ chunk_id (unik)            │
│                    └────────────────────┘                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           RETRIEVAL PIPELINE                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Query              Smart Retriever                    LLM                   │
│  ┌──────────┐      ┌────────────────────────────┐     ┌──────────────┐      │
│  │ "Berapa  │      │ 1. Get top-K chunks        │     │              │      │
│  │  biaya   │ ──▶  │                            │     │   Generate   │      │
│  │  SPP?"   │      │ 2. Extract document_ids    │ ──▶ │   Answer     │      │
│  └──────────┘      │    (chunks mana yg relevan)│     │              │      │
│                    │                            │     └──────────────┘      │
│                    │ 3. Fetch ALL chunks        │                            │
│                    │    per document_id         │     Context yang           │
│                    │                            │     dikirim ke LLM:        │
│                    │ 4. Sort by chunk_index     │     ┌──────────────┐      │
│                    │                            │     │ [Dokumen 1]  │      │
│                    │ 5. MERGE chunks            │     │ Chunk 0 + 1  │      │
│                    │    jadi dokumen utuh       │     │ + 2 + 3 ...  │      │
│                    └────────────────────────────┘     │ (LENGKAP!)   │      │
│                                                       └──────────────┘      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔑 Konsep Kunci

### 1. Document ID yang Konsisten

**Masalah Sebelumnya:**
- Chunks dari dokumen yang sama punya ID berbeda-beda
- Tidak bisa menggabungkan chunks saat retrieval

**Solusi:**
```python
def _generate_document_id(self, source: str, content: str) -> str:
    """
    Generate document_id berdasarkan source + content hash
    SEMUA chunks dari dokumen yang sama punya document_id SAMA
    """
    content_preview = content[:500]
    unique_string = f"{source}_{hashlib.md5(content_preview.encode()).hexdigest()[:8]}"
    return unique_string
```

### 2. Metadata Lengkap per Chunk

Setiap chunk menyimpan:
```python
chunk_metadata = {
    # Identifikasi dokumen
    "document_id": "brosur_biaya_2024_a1b2c3d4",  # SAMA untuk semua chunks
    "chunk_id": "brosur_biaya_2024_a1b2c3d4_chunk_0001",
    
    # Posisi dalam dokumen
    "chunk_index": 0,
    "total_chunks": 5,
    "is_first_chunk": True,
    "is_last_chunk": False,
    
    # Navigasi
    "prev_chunk_id": None,
    "next_chunk_id": "brosur_biaya_2024_a1b2c3d4_chunk_0002",
    
    # Metadata asli
    "source": "brosur_biaya_2024.pdf",
    "jenjang": "SD",
    "tahun": "2024/2025",
    "cabang": "Pusat"
}
```

### 3. Document Aggregation saat Retrieval

```python
def _aggregate_by_document(self, initial_docs, verbose):
    """
    KUNCI: Fetch SEMUA chunks dari dokumen yang sama
    """
    
    # 1. Group hasil retrieval by document_id
    docs_by_id = defaultdict(list)
    for doc in initial_docs:
        doc_id = doc.metadata.get('document_id')
        docs_by_id[doc_id].append(doc)
    
    # 2. Untuk setiap dokumen unik, fetch SEMUA chunks
    for doc_id in docs_by_id.keys():
        all_chunks = self._fetch_all_chunks_for_document(doc_id)
        
        # 3. Sort by chunk_index
        all_chunks.sort(key=lambda x: x.metadata.get('chunk_index', 0))
        
        # 4. Merge jadi satu dokumen
        merged = self._merge_chunks(all_chunks)
```

---

## 📁 Struktur File

```
rag_solution/
├── config/
│   └── config.yaml         # Konfigurasi RAG
├── core/
│   └── rag_factory.py      # Factory pattern untuk components
├── utils/
│   ├── enhanced_chunker.py # Chunker dengan document tracking
│   └── smart_retriever.py  # Retriever dengan aggregation
├── api/
│   ├── chat_router.py      # Chat endpoint
│   └── ingestion_router.py # Ingestion endpoint
└── main.py                 # FastAPI app
```

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install fastapi uvicorn langchain langchain-openai langchain-chroma chromadb pydantic python-dotenv pyyaml
```

### 2. Set Environment

```bash
# .env
OPENAI_API_KEY=sk-xxx
```

### 3. Ingest Document

```python
from core.rag_factory import get_chunker, get_vectorstore

# Chunk document
chunker = get_chunker()
chunks = chunker.chunk_document(
    content="Biaya SPP SD tahun 2024/2025 adalah Rp 1.500.000...",
    metadata={
        "source": "brosur_biaya_2024.pdf",
        "jenjang": "SD",
        "tahun": "2024/2025"
    }
)

# Store ke vectorstore
vectorstore = get_vectorstore()
vectorstore.add_documents(
    documents=chunks,
    ids=[c.metadata['chunk_id'] for c in chunks]
)
```

### 4. Query

```python
from core.rag_factory import get_query_chain

chain = get_query_chain()
result = chain.query("Berapa biaya SPP SD?")

print(result['answer'])
print(result['sources'])
```

---

## 🔧 API Endpoints

### Chat

```bash
# Simple chat
POST /api/v1/chat/
{
    "question": "Berapa biaya SPP SD tahun 2024?",
    "verbose": false
}

# Test retrieval (tanpa LLM)
POST /api/v1/chat/test-retrieval
{
    "query": "biaya SPP",
    "top_k": 5,
    "fetch_full_document": true
}

# Debug vectorstore
GET /api/v1/chat/debug
```

### Ingestion

```bash
# Ingest single document
POST /api/v1/ingest/document
{
    "content": "...",
    "metadata": {
        "source": "brosur.pdf",
        "jenjang": "SD",
        "tahun": "2024"
    }
}

# List documents
GET /api/v1/ingest/status

# Get chunks for document
GET /api/v1/ingest/document/{document_id}/chunks

# Delete document
DELETE /api/v1/ingest/document/{document_id}
```

---

## 📊 Debug VectorStore

### Cek Struktur

```python
from core.rag_factory import inspect_vectorstore

info = inspect_vectorstore()
print(f"Total chunks: {info['total_chunks']}")
print(f"Unique documents: {info['unique_documents']}")
print(f"Document IDs: {info['document_ids']}")
print(f"Sample metadata: {info['sample_metadata']}")
```

### Cek Document Aggregation

```python
from core.rag_factory import get_retriever

retriever = get_retriever()
docs = retriever.retrieve("biaya SPP", verbose=True)

for doc in docs:
    print(f"Document ID: {doc.metadata['document_id']}")
    print(f"Merged chunks: {doc.metadata.get('merged_chunks', 1)}")
    print(f"Content length: {len(doc.page_content)}")
```

---

## ⚙️ Tuning Parameters

### Chunking

```yaml
chunking:
  fixed_size:
    # Dokumen informatif (brosur, FAQ)
    chunk_size: 800
    chunk_overlap: 150
    
    # Dokumen panjang (prosedur, regulasi)
    chunk_size: 1200
    chunk_overlap: 250
```

### Retrieval

```yaml
retrieval:
  # Jumlah chunks awal
  top_k: 5
  
  # Similarity minimum (0.5 = cukup relevan)
  similarity_threshold: 0.5
  
  # Max dokumen unik (3 = balance antara detail dan noise)
  max_documents: 3
  
  # PENTING: true untuk menggabungkan chunks
  fetch_full_document: true
```

---

## 🔍 Troubleshooting

### 1. Chunks Tidak Tergabung

**Cek document_id:**
```python
results = vectorstore._collection.get(include=['metadatas'])
for meta in results['metadatas']:
    print(meta.get('document_id'))
```

**Pastikan document_id konsisten:**
- Semua chunks dari file yang sama harus punya document_id sama

### 2. Informasi Masih Terpotong

**Increase chunk_size:**
```yaml
chunking:
  fixed_size:
    chunk_size: 1500  # Lebih besar
    chunk_overlap: 300
```

**Atau increase max_documents:**
```yaml
retrieval:
  max_documents: 5  # Lebih banyak dokumen
```

### 3. Hasil Tidak Relevan

**Turunkan similarity_threshold:**
```yaml
retrieval:
  similarity_threshold: 0.4  # Lebih permisif
```

---

## 🏗️ Integrasi dengan Kode Existing

### Ganti Chunker

```python
# SEBELUM (existing)
from langchain_text_splitters import RecursiveCharacterTextSplitter
splitter = RecursiveCharacterTextSplitter(chunk_size=1000)
chunks = splitter.split_text(content)

# SESUDAH (enhanced)
from utils.enhanced_chunker import EnhancedChunker
chunker = EnhancedChunker(config=config)
chunks = chunker.chunk_document(content, metadata)
# chunks sekarang punya document_id yang konsisten!
```

### Ganti Retriever

```python
# SEBELUM (existing)
docs = vectorstore.similarity_search(query, k=5)

# SESUDAH (smart)
from utils.smart_retriever import SmartRetriever
retriever = SmartRetriever(
    vectorstore=vectorstore,
    embedding_function=embeddings,
    fetch_full_document=True  # KUNCI!
)
docs = retriever.retrieve(query)
# docs sekarang sudah digabungkan per dokumen!
```

---

## 📝 Catatan Penting

1. **document_id HARUS konsisten** - Semua chunks dari dokumen yang sama WAJIB punya document_id yang sama. Ini adalah kunci untuk aggregation.

2. **Re-ingest jika perlu** - Jika data existing tidak punya document_id yang konsisten, perlu re-ingest dengan chunker baru.

3. **Balance chunk_size** - Terlalu kecil = konteks terpotong, terlalu besar = noise. Rekomendasi: 800-1200 chars.

4. **fetch_full_document = true** - Ini yang memungkinkan penggabungan chunks. Jangan dimatikan kecuali untuk testing.

5. **Monitor context length** - Pastikan total context tidak melebihi context window LLM (biasanya 4K-128K tokens).

---

## 🔄 Migration dari Kode Existing

Jika Anda sudah punya data di ChromaDB tanpa document_id yang konsisten:

```python
# Script migration
from core.rag_factory import get_vectorstore, get_chunker

vectorstore = get_vectorstore()
chunker = get_chunker()

# 1. Export existing data
collection = vectorstore._collection
all_data = collection.get(include=['documents', 'metadatas'])

# 2. Group by source (asumsi source adalah identifier)
from collections import defaultdict
docs_by_source = defaultdict(list)

for content, metadata in zip(all_data['documents'], all_data['metadatas']):
    source = metadata.get('source', 'unknown')
    docs_by_source[source].append({
        'content': content,
        'metadata': metadata
    })

# 3. Re-chunk dengan document_id baru
new_chunks = []
for source, docs in docs_by_source.items():
    # Gabungkan content dari chunks yang sama source
    full_content = "\n\n".join([d['content'] for d in docs])
    base_metadata = docs[0]['metadata']
    
    # Chunk ulang
    chunks = chunker.chunk_document(full_content, base_metadata)
    new_chunks.extend(chunks)

# 4. Clear dan re-populate
# HATI-HATI: Ini akan menghapus data lama!
collection.delete(ids=all_data['ids'])

# Add new chunks
vectorstore.add_documents(
    documents=new_chunks,
    ids=[c.metadata['chunk_id'] for c in new_chunks]
)

print(f"Migrated {len(new_chunks)} chunks")
```

---

## 📈 Performance Tips

### 1. Batch Embedding

```python
# Untuk dokumen banyak, gunakan batch
chunker = get_chunker()
all_chunks = []

for doc in documents:
    chunks = chunker.chunk_document(doc['content'], doc['metadata'])
    all_chunks.extend(chunks)

# Batch add (lebih efisien)
vectorstore.add_documents(
    documents=all_chunks,
    ids=[c.metadata['chunk_id'] for c in all_chunks]
)
```

### 2. Caching Query Chain

```python
# Query chain sudah singleton, jadi aman dipanggil berkali-kali
chain = get_query_chain()  # Hanya init sekali

# Subsequent calls return same instance
chain = get_query_chain()  # Tidak init ulang
```

---

## 🧪 Testing

### Unit Test Chunker

```python
def test_document_id_consistency():
    chunker = EnhancedChunker(config=config)
    
    content = "Lorem ipsum dolor sit amet..." * 100
    metadata = {"source": "test.pdf"}
    
    chunks = chunker.chunk_document(content, metadata)
    
    # Semua chunks harus punya document_id yang sama
    doc_ids = set(c.metadata['document_id'] for c in chunks)
    assert len(doc_ids) == 1, "document_id tidak konsisten!"
    
    # Chunk index harus berurutan
    indices = [c.metadata['chunk_index'] for c in chunks]
    assert indices == list(range(len(chunks))), "chunk_index tidak urut!"
```

### Integration Test

```python
def test_retrieval_aggregation():
    # Ingest test document
    chunker = get_chunker()
    vectorstore = get_vectorstore()
    
    content = "Bagian 1: Biaya SPP\n" * 50 + "Bagian 2: Pendaftaran\n" * 50
    chunks = chunker.chunk_document(content, {"source": "test_doc.pdf"})
    
    vectorstore.add_documents(chunks, ids=[c.metadata['chunk_id'] for c in chunks])
    
    # Retrieve
    retriever = get_retriever()
    docs = retriever.retrieve("biaya SPP")
    
    # Harus ada aggregation
    assert len(docs) > 0
    assert docs[0].metadata.get('is_aggregated', False) == True
    assert docs[0].metadata.get('merged_chunks', 0) > 1
```

---

## 🤝 Summary

**Key Improvements:**
1. ✅ Document ID konsisten untuk semua chunks dari dokumen yang sama
2. ✅ Chunk metadata lengkap dengan navigasi (prev/next)
3. ✅ Smart retrieval dengan document aggregation
4. ✅ Debug endpoints untuk troubleshooting
5. ✅ Migration support untuk data existing

**Flow Ringkas:**
```
Dokumen → Chunk (dengan document_id sama) → Embed → Store
Query → Retrieve top-K → Group by document_id → Fetch ALL chunks → Merge → LLM
```

Dengan solusi ini, informasi tidak akan terpotong karena semua chunks dari dokumen yang sama akan digabungkan sebelum dikirim ke LLM.
