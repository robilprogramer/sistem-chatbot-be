# ============================================================================
# FILE: informasional/utils/enhanced_chunker.py
# ============================================================================
"""
Enhanced Chunker dengan Document ID Konsisten
- Setiap chunk memiliki document_id yang SAMA untuk 1 dokumen
- Mendukung penggabungan chunks saat retrieval
"""

import hashlib
from typing import List, Dict, Any
from datetime import datetime
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
import yaml


class EnhancedChunker:
    """
    Enhanced Text Chunker dengan Document ID Tracking
    
    Key Features:
    1. document_id KONSISTEN untuk semua chunks dari 1 dokumen
    2. chunk_index untuk ordering
    3. Metadata lengkap untuk retrieval dan aggregation
    """
    
    def __init__(self, config_path: str = None, config: Dict = None):
        if config:
            self.config = config
        elif config_path:
            self.config = self._load_config(config_path)
        else:
            self.config = self._default_config()
        
        self.chunking_cfg = self.config.get("chunking", {})
        self.strategy = self.chunking_cfg.get("strategy", "fixed_size")
        self.splitter = self._build_fixed_size_splitter()
    
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
    
    def _load_config(self, path: str) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    def _build_fixed_size_splitter(self) -> RecursiveCharacterTextSplitter:
        cfg = self.chunking_cfg.get("fixed_size", {})
        return RecursiveCharacterTextSplitter(
            chunk_size=cfg.get("chunk_size", 1000),
            chunk_overlap=cfg.get("chunk_overlap", 200),
            separators=cfg.get("separators", ["\n\n", "\n", ".", " ", ""]),
            length_function=len,
        )
    
    def _generate_document_id(self, source: str, content: str) -> str:
        """
        Generate document_id yang KONSISTEN
        Semua chunks dari dokumen yang sama punya document_id SAMA
        """
        # Gunakan source + hash dari content awal untuk identifikasi unik
        content_preview = content[:500] if len(content) > 500 else content
        hash_part = hashlib.md5(content_preview.encode()).hexdigest()[:8]
        
        # Clean source name
        clean_source = source.replace(" ", "_").replace("/", "_")
        
        return f"{clean_source}_{hash_part}"
    
    def _generate_chunk_id(self, document_id: str, chunk_index: int) -> str:
        """Generate unique chunk_id"""
        return f"{document_id}_chunk_{chunk_index:04d}"
    
    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize metadata untuk kompatibilitas ChromaDB
        ChromaDB hanya support: str, int, float, bool
        """
        safe = {}
        for k, v in metadata.items():
            if v is None:
                safe[k] = ""
            elif isinstance(v, bool):
                safe[k] = v
            elif isinstance(v, (int, float)):
                safe[k] = v
            elif isinstance(v, str):
                safe[k] = v
            elif isinstance(v, list):
                safe[k] = ", ".join(str(item) for item in v)
            elif isinstance(v, dict):
                safe[k] = str(v)
            else:
                safe[k] = str(v)
        return safe
    
    def chunk_with_metadata(
        self,
        content: str,
        metadata: Dict[str, Any],
        source_document_id: int = None  # ID dari table documents
    ) -> List[Document]:
        """
        Chunk dokumen dengan metadata tracking lengkap
        
        Args:
            content: Isi dokumen
            metadata: Metadata dokumen (source, jenjang, tahun, dll)
            source_document_id: ID dari table documents (opsional)
        
        Returns:
            List of Document dengan metadata lengkap
        """
        if not content or not content.strip():
            return []
        
        # Generate consistent document_id
        source = metadata.get("source", metadata.get("filename", "unknown"))
        document_id = self._generate_document_id(source, content)
        
        # Split content
        chunks_text = self.splitter.split_text(content)
        total_chunks = len(chunks_text)
        
        # Build documents dengan metadata lengkap
        documents: List[Document] = []
        
        for idx, chunk_text in enumerate(chunks_text):
            chunk_id = self._generate_chunk_id(document_id, idx)
            
            # Build comprehensive metadata
            chunk_metadata = {
                # ===== DOCUMENT TRACKING (KUNCI) =====
                "document_id": document_id,
                "chunk_id": chunk_id,
                "chunk_index": idx,
                "total_chunks": total_chunks,
                
                # ===== SOURCE REFERENCE =====
                "source_document_id": source_document_id,
                
                # ===== POSITION FLAGS =====
                "is_first_chunk": idx == 0,
                "is_last_chunk": idx == total_chunks - 1,
                
                # ===== NAVIGATION =====
                "prev_chunk_id": self._generate_chunk_id(document_id, idx - 1) if idx > 0 else None,
                "next_chunk_id": self._generate_chunk_id(document_id, idx + 1) if idx < total_chunks - 1 else None,
                
                # ===== ORIGINAL METADATA =====
                "source": source,
                "filename": metadata.get("filename", source),
                "jenjang": metadata.get("jenjang", ""),
                "cabang": metadata.get("cabang", ""),
                "tahun": metadata.get("tahun", ""),
                "category": metadata.get("category", ""),
                
                # ===== CHUNK INFO =====
                "chunk_length": len(chunk_text),
                "chunk_strategy": self.strategy,
                "chunked_at": datetime.now().isoformat(),
            }
            
            # Merge dengan metadata tambahan
            for key, value in metadata.items():
                if key not in chunk_metadata:
                    # Sanitize untuk ChromaDB compatibility
                    if isinstance(value, list):
                        chunk_metadata[key] = ", ".join(str(v) for v in value)
                    elif value is None:
                        chunk_metadata[key] = ""
                    else:
                        chunk_metadata[key] = value
            
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
            documents: List of dict dengan keys: content, metadata, source_document_id (optional)
        
        Returns:
            List of all chunks
        """
        all_chunks: List[Document] = []
        
        for doc in documents:
            content = doc.get("content", "")
            metadata = doc.get("metadata", {})
            source_doc_id = doc.get("source_document_id")
            
            chunks = self.chunk_with_metadata(content, metadata, source_doc_id)
            all_chunks.extend(chunks)
        
        return all_chunks
    
    def get_statistics(self, documents: List[Document]) -> Dict[str, Any]:
        """Get chunking statistics"""
        if not documents:
            return {"total_chunks": 0}
        
        lengths = [len(doc.page_content) for doc in documents]
        
        # Group by document_id
        docs_by_id = {}
        sources = {}
        jenjang_dist = {}
        
        for doc in documents:
            doc_id = doc.metadata.get("document_id", "unknown")
            if doc_id not in docs_by_id:
                docs_by_id[doc_id] = []
            docs_by_id[doc_id].append(doc)
            
            src = doc.metadata.get("source", "Unknown")
            sources[src] = sources.get(src, 0) + 1
            
            lvl = doc.metadata.get("jenjang", "Unknown")
            jenjang_dist[lvl] = jenjang_dist.get(lvl, 0) + 1
        
        return {
            "strategy": self.strategy,
            "total_chunks": len(documents),
            "total_documents": len(docs_by_id),
            "avg_length": int(sum(lengths) / len(lengths)),
            "min_length": min(lengths),
            "max_length": max(lengths),
            "total_chars": sum(lengths),
            "sources": sources,
            "jenjang_distribution": jenjang_dist,
            "chunks_per_document": {doc_id: len(chunks) for doc_id, chunks in docs_by_id.items()}
        }


# ============================================================================
# DOCUMENT PROCESSOR
# ============================================================================
class DocumentProcessor:
    """
    High-level processor untuk dokumen
    """
    
    def __init__(self, chunker: EnhancedChunker, metadata_extractor=None):
        self.chunker = chunker
        self.metadata_extractor = metadata_extractor
    
    def process_document(
        self,
        filename: str,
        content: str,
        metadata: Dict[str, Any] = None,
        source_document_id: int = None,
        use_semantic: bool = False  # Untuk backward compatibility
    ) -> List[Document]:
        """
        Process single document
        """
        print(f"\n📄 Processing: {filename}")
        
        # Build metadata
        if metadata is None:
            metadata = {}
        
        if self.metadata_extractor and not metadata:
            metadata = self.metadata_extractor.extract_full(filename, content)
            print("   🔍 Metadata extracted automatically")
        else:
            print("   ✅ Using provided metadata")
        
        metadata["source"] = metadata.get("source", filename)
        metadata["filename"] = filename
        
        # Chunk
        chunks = self.chunker.chunk_with_metadata(
            content=content,
            metadata=metadata,
            source_document_id=source_document_id
        )
        
        print(f"   ✂️ Created {len(chunks)} chunks")
        if chunks:
            print(f"   🔑 Document ID: {chunks[0].metadata['document_id']}")
        
        return chunks
    
    def process_multiple_documents(
        self,
        documents: List[Dict[str, Any]]
    ) -> List[Document]:
        """Process multiple documents"""
        all_chunks: List[Document] = []
        
        for doc in documents:
            chunks = self.process_document(
                filename=doc.get("filename", "unknown.pdf"),
                content=doc.get("content", ""),
                metadata=doc.get("metadata", {}),
                source_document_id=doc.get("source_document_id"),
                use_semantic=doc.get("use_semantic", False)
            )
            all_chunks.extend(chunks)
        
        # Print statistics
        stats = self.chunker.get_statistics(all_chunks)
        print(f"\n📊 Total chunks: {stats['total_chunks']}")
        print(f"   Total documents: {stats['total_documents']}")
        print(f"   Avg length: {stats['avg_length']} chars")
        
        return all_chunks
