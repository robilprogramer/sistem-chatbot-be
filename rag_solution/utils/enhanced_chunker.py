# ============================================================================
# FILE: utils/enhanced_chunker.py
# ============================================================================
"""
Enhanced Chunker dengan Parent-Child Relationship
- Setiap chunk memiliki document_id yang KONSISTEN
- Mendukung penggabungan chunks dari dokumen yang sama saat retrieval
"""

import hashlib
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
import yaml


class EnhancedChunker:
    """
    Enhanced Text Chunker dengan Document Tracking
    
    Key Features:
    1. document_id KONSISTEN untuk semua chunks dari 1 dokumen
    2. chunk_index untuk ordering
    3. parent_content hash untuk validasi integritas
    4. Metadata lengkap untuk retrieval
    """
    
    def __init__(self, config_path: str = None, config: Dict = None):
        if config:
            self.config = config
        elif config_path:
            self.config = self._load_config(config_path)
        else:
            self.config = self._default_config()
        
        self.chunking_cfg = self.config.get("chunking", {})
        self.splitter = self._build_splitter()
    
    def _default_config(self) -> Dict:
        return {
            "chunking": {
                "strategy": "fixed_size",
                "fixed_size": {
                    "chunk_size": 1000,
                    "chunk_overlap": 200,
                    "separators": ["\n\n", "\n", ".", " ", ""]
                }
            }
        }
    
    def _load_config(self, path: str) -> Dict:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    def _build_splitter(self) -> RecursiveCharacterTextSplitter:
        cfg = self.chunking_cfg.get("fixed_size", {})
        return RecursiveCharacterTextSplitter(
            chunk_size=cfg.get("chunk_size", 1000),
            chunk_overlap=cfg.get("chunk_overlap", 200),
            separators=cfg.get("separators", ["\n\n", "\n", ".", " ", ""]),
            length_function=len,
            add_start_index=True,  # Track posisi dalam dokumen asli
        )
    
    def _generate_document_id(self, source: str, content: str) -> str:
        """
        Generate document_id yang KONSISTEN berdasarkan source + content hash
        Ini memastikan chunks dari dokumen yang sama punya document_id yang sama
        """
        # Gunakan source + hash dari konten (first 500 chars) untuk identifikasi
        content_preview = content[:500] if len(content) > 500 else content
        unique_string = f"{source}_{hashlib.md5(content_preview.encode()).hexdigest()[:8]}"
        return unique_string
    
    def _generate_chunk_id(self, document_id: str, chunk_index: int) -> str:
        """Generate unique chunk_id"""
        return f"{document_id}_chunk_{chunk_index:04d}"
    
    def chunk_document(
        self,
        content: str,
        metadata: Dict[str, Any],
        use_overlap_context: bool = True
    ) -> List[Document]:
        """
        Chunk dokumen dengan metadata tracking yang lengkap
        
        Args:
            content: Isi dokumen
            metadata: Metadata dokumen (source, jenjang, tahun, cabang, dll)
            use_overlap_context: Tambahkan context dari chunk sebelumnya
        
        Returns:
            List of Document dengan metadata lengkap
        """
        if not content or not content.strip():
            return []
        
        # Generate consistent document_id
        source = metadata.get("source", f"doc_{uuid.uuid4().hex[:8]}")
        document_id = self._generate_document_id(source, content)
        
        # Split content
        texts_with_metadata = self.splitter.create_documents(
            texts=[content],
            metadatas=[metadata]
        )
        
        # Extract just the texts for processing
        chunks_text = [doc.page_content for doc in texts_with_metadata]
        total_chunks = len(chunks_text)
        
        # Build documents dengan metadata lengkap
        documents: List[Document] = []
        
        for idx, chunk_text in enumerate(chunks_text):
            chunk_id = self._generate_chunk_id(document_id, idx)
            
            # Build comprehensive metadata
            chunk_metadata = {
                # Document identification (CRITICAL untuk penggabungan)
                "document_id": document_id,
                "chunk_id": chunk_id,
                "chunk_index": idx,
                "total_chunks": total_chunks,
                
                # Position info
                "is_first_chunk": idx == 0,
                "is_last_chunk": idx == total_chunks - 1,
                
                # Original metadata
                "source": source,
                "jenjang": metadata.get("jenjang", ""),
                "cabang": metadata.get("cabang", ""),
                "tahun": metadata.get("tahun", ""),
                "category": metadata.get("category", ""),
                
                # Chunk info
                "chunk_length": len(chunk_text),
                "chunked_at": datetime.now().isoformat(),
                
                # Navigation (untuk context window)
                "prev_chunk_id": self._generate_chunk_id(document_id, idx - 1) if idx > 0 else None,
                "next_chunk_id": self._generate_chunk_id(document_id, idx + 1) if idx < total_chunks - 1 else None,
            }
            
            # Merge dengan metadata asli (jika ada field tambahan)
            for key, value in metadata.items():
                if key not in chunk_metadata:
                    # Sanitize untuk ChromaDB compatibility
                    if isinstance(value, list):
                        chunk_metadata[key] = ", ".join(str(v) for v in value)
                    elif value is None:
                        chunk_metadata[key] = ""
                    else:
                        chunk_metadata[key] = value
            
            # Optional: Add context dari chunk sebelumnya
            if use_overlap_context and idx > 0:
                # Simpan preview dari chunk sebelumnya untuk context
                prev_text = chunks_text[idx - 1]
                chunk_metadata["prev_chunk_preview"] = prev_text[-200:] if len(prev_text) > 200 else prev_text
            
            documents.append(
                Document(
                    page_content=chunk_text,
                    metadata=chunk_metadata
                )
            )
        
        return documents
    
    def chunk_multiple_documents(
        self,
        documents: List[Dict[str, Any]]
    ) -> List[Document]:
        """
        Process multiple documents
        
        Args:
            documents: List of dict dengan keys: content, metadata
        
        Returns:
            List of all chunks
        """
        all_chunks: List[Document] = []
        
        for doc in documents:
            content = doc.get("content", "")
            metadata = doc.get("metadata", {})
            
            chunks = self.chunk_document(content, metadata)
            all_chunks.extend(chunks)
        
        return all_chunks
    
    def get_statistics(self, documents: List[Document]) -> Dict[str, Any]:
        """Get chunking statistics"""
        if not documents:
            return {"total_chunks": 0}
        
        lengths = [len(doc.page_content) for doc in documents]
        
        # Group by document_id
        docs_by_id = {}
        for doc in documents:
            doc_id = doc.metadata.get("document_id", "unknown")
            if doc_id not in docs_by_id:
                docs_by_id[doc_id] = []
            docs_by_id[doc_id].append(doc)
        
        return {
            "total_chunks": len(documents),
            "total_documents": len(docs_by_id),
            "avg_chunk_length": int(sum(lengths) / len(lengths)),
            "min_chunk_length": min(lengths),
            "max_chunk_length": max(lengths),
            "total_chars": sum(lengths),
            "chunks_per_document": {
                doc_id: len(chunks) for doc_id, chunks in docs_by_id.items()
            }
        }


# ============================================================================
# DOCUMENT PROCESSOR (dengan Metadata Extractor)
# ============================================================================
class DocumentProcessor:
    """
    High-level processor untuk dokumen
    """
    
    def __init__(self, chunker: EnhancedChunker):
        self.chunker = chunker
    
    def process_document(
        self,
        filename: str,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> List[Document]:
        """
        Process single document
        """
        print(f"\n📄 Processing: {filename}")
        
        # Build metadata
        if metadata is None:
            metadata = {}
        
        metadata["source"] = metadata.get("source", filename)
        metadata["filename"] = filename
        
        # Chunk
        chunks = self.chunker.chunk_document(content, metadata)
        
        print(f"   ✂️ Created {len(chunks)} chunks")
        print(f"   🔑 Document ID: {chunks[0].metadata['document_id'] if chunks else 'N/A'}")
        
        return chunks
    
    def process_batch(
        self,
        documents: List[Dict[str, Any]]
    ) -> List[Document]:
        """Process multiple documents"""
        all_chunks = []
        
        for doc in documents:
            chunks = self.process_document(
                filename=doc.get("filename", "unknown.pdf"),
                content=doc.get("content", ""),
                metadata=doc.get("metadata", {})
            )
            all_chunks.extend(chunks)
        
        # Print statistics
        stats = self.chunker.get_statistics(all_chunks)
        print(f"\n📊 Statistics:")
        print(f"   Total chunks: {stats['total_chunks']}")
        print(f"   Total documents: {stats['total_documents']}")
        print(f"   Avg chunk length: {stats['avg_chunk_length']} chars")
        
        return all_chunks


# ============================================================================
# QUICK TEST
# ============================================================================
if __name__ == "__main__":
    # Test chunking
    config = {
        "chunking": {
            "fixed_size": {
                "chunk_size": 500,
                "chunk_overlap": 100,
                "separators": ["\n\n", "\n", ".", " ", ""]
            }
        }
    }
    
    chunker = EnhancedChunker(config=config)
    
    # Sample document
    sample_content = """
    YPI Al-Azhar Jakarta adalah yayasan pendidikan Islam terkemuka.
    
    Biaya Pendidikan Tahun 2024/2025:
    - SPP SD: Rp 1.500.000/bulan
    - SPP SMP: Rp 1.800.000/bulan
    - SPP SMA: Rp 2.000.000/bulan
    
    Program unggulan meliputi:
    1. Tahfidz Al-Quran
    2. Bilingual Program
    3. Science Club
    
    Pendaftaran dibuka setiap tahun mulai Januari.
    Untuk informasi lebih lanjut, hubungi (021) 1234567.
    """ * 3  # Repeat untuk content lebih panjang
    
    metadata = {
        "source": "brosur_biaya_2024.pdf",
        "jenjang": "SD, SMP, SMA",
        "tahun": "2024/2025",
        "cabang": "Pusat"
    }
    
    chunks = chunker.chunk_document(sample_content, metadata)
    
    print(f"\n{'='*60}")
    print("CHUNKING TEST RESULTS")
    print(f"{'='*60}")
    print(f"Total chunks: {len(chunks)}")
    
    for i, chunk in enumerate(chunks):
        print(f"\n--- Chunk {i+1} ---")
        print(f"ID: {chunk.metadata['chunk_id']}")
        print(f"Document ID: {chunk.metadata['document_id']}")
        print(f"Index: {chunk.metadata['chunk_index']}/{chunk.metadata['total_chunks']}")
        print(f"Length: {chunk.metadata['chunk_length']} chars")
        print(f"Content preview: {chunk.page_content[:100]}...")
