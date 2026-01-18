"""
Enhanced Chunker dengan Document ID Konsisten

Features:
1. document_id KONSISTEN untuk semua chunks dari 1 dokumen
2. chunk_index untuk ordering
3. Metadata lengkap untuk retrieval dan aggregation
4. Semua konfigurasi dari YAML file
"""

import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import yaml

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document


class ChunkerConfig:
    """
    Configuration loader untuk Chunker
    Memastikan semua config dibaca dari YAML
    """
    
    def __init__(self, config_path: str = None, config_dict: Dict = None):
        if config_dict:
            self._config = config_dict
        elif config_path:
            self._config = self._load_yaml(config_path)
        else:
            raise ValueError("Either config_path or config_dict must be provided")
        
        self._chunking = self._config.get("chunking", {})
    
    def _load_yaml(self, path: str) -> Dict[str, Any]:
        """Load YAML config file"""
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    @property
    def strategy(self) -> str:
        """Get chunking strategy: fixed_size, semantic, or hybrid"""
        return self._chunking.get("strategy", "fixed_size")
    
    @property
    def fixed_size(self) -> Dict[str, Any]:
        """Get fixed_size chunking config"""
        defaults = {
            "chunk_size": 1000,
            "chunk_overlap": 200,
            "separators": ["\n\n", "\n", ".", " ", ""]
        }
        cfg = self._chunking.get("fixed_size", {})
        return {**defaults, **cfg}
    
    @property
    def semantic(self) -> Dict[str, Any]:
        """Get semantic chunking config"""
        defaults = {
            "use_openai": True,
            "model_name": "text-embedding-3-small",
            "breakpoint_threshold_type": "percentile",
            "breakpoint_threshold": 95,
            "min_length": 1200
        }
        cfg = self._chunking.get("semantic", {})
        return {**defaults, **cfg}
    
    @property
    def hybrid(self) -> Dict[str, Any]:
        """Get hybrid chunking config"""
        defaults = {
            "length_threshold": 3000,
            "fallback_to_fixed": True
        }
        cfg = self._chunking.get("hybrid", {})
        return {**defaults, **cfg}
    
    def get_full_config(self) -> Dict[str, Any]:
        """Get full chunking configuration"""
        return {
            "strategy": self.strategy,
            "fixed_size": self.fixed_size,
            "semantic": self.semantic,
            "hybrid": self.hybrid
        }


class EnhancedChunker:
    """
    Enhanced Text Chunker dengan Document ID Tracking
    
    Semua konfigurasi dibaca dari YAML file.
    
    Usage:
        chunker = EnhancedChunker(config_path="config/config.yaml")
        chunks = chunker.chunk_document(content, metadata)
    """
    
    def __init__(self, config_path: str = None, config: Dict = None):
        """
        Initialize chunker
        
        Args:
            config_path: Path ke file YAML config
            config: Dictionary config (alternatif dari YAML)
        """
        # Load configuration
        self._cfg = ChunkerConfig(config_path=config_path, config_dict=config)
        
        # Initialize splitter based on strategy
        self._splitter = self._build_splitter()
        
        # Log configuration
        self._log_config()
    
    def _log_config(self):
        """Log current configuration"""
        cfg = self._cfg.get_full_config()
        print(f"📋 Chunker initialized with strategy: {cfg['strategy']}")
        
        if cfg['strategy'] in ['fixed_size', 'hybrid']:
            fs = cfg['fixed_size']
            print(f"   └─ chunk_size: {fs['chunk_size']}, overlap: {fs['chunk_overlap']}")
    
    def _build_splitter(self) -> RecursiveCharacterTextSplitter:
        """Build text splitter based on config"""
        fs_cfg = self._cfg.fixed_size
        
        return RecursiveCharacterTextSplitter(
            chunk_size=fs_cfg["chunk_size"],
            chunk_overlap=fs_cfg["chunk_overlap"],
            separators=fs_cfg["separators"],
            length_function=len,
        )
    
    @property
    def strategy(self) -> str:
        """Current chunking strategy"""
        return self._cfg.strategy
    
    @property
    def config(self) -> Dict[str, Any]:
        """Full chunking configuration"""
        return self._cfg.get_full_config()
    
    # =========================================================================
    # DOCUMENT ID GENERATION
    # =========================================================================
    
    def _generate_document_id(self, source: str, content: str) -> str:
        """
        Generate document_id yang KONSISTEN
        
        Semua chunks dari dokumen yang sama punya document_id SAMA.
        Format: {clean_source}_{content_hash}
        """
        # Use content preview for hash
        content_preview = content[:500] if len(content) > 500 else content
        hash_part = hashlib.md5(content_preview.encode()).hexdigest()[:8]
        
        # Clean source name
        clean_source = source.replace(" ", "_").replace("/", "_").replace("\\", "_")
        
        # Remove extension if present
        clean_source = Path(clean_source).stem
        
        return f"{clean_source}_{hash_part}"
    
    def _generate_chunk_id(self, document_id: str, chunk_index: int) -> str:
        """Generate unique chunk_id"""
        return f"{document_id}_chunk_{chunk_index:04d}"
    
    # =========================================================================
    # MAIN CHUNKING METHOD
    # =========================================================================
    
    def chunk_document(
        self,
        content: str,
        metadata: Dict[str, Any],
        source_document_id: int = None
    ) -> List[Document]:
        """
        Chunk dokumen dengan metadata tracking lengkap
        
        Args:
            content: Isi dokumen
            metadata: Metadata dokumen (source, jenjang, tahun, dll)
            source_document_id: ID dari table documents (untuk FK)
        
        Returns:
            List of Document dengan metadata lengkap
        """
        if not content or not content.strip():
            return []
        
        # Get source for document_id
        source = metadata.get("source", metadata.get("filename", "unknown"))
        
        # Generate consistent document_id
        document_id = self._generate_document_id(source, content)
        
        # Split content
        chunks_text = self._splitter.split_text(content)
        total_chunks = len(chunks_text)
        
        if total_chunks == 0:
            return []
        
        # Build documents dengan metadata
        documents: List[Document] = []
        
        for idx, chunk_text in enumerate(chunks_text):
            chunk_id = self._generate_chunk_id(document_id, idx)
            
            # Build chunk metadata
            chunk_metadata = self._build_chunk_metadata(
                document_id=document_id,
                chunk_id=chunk_id,
                chunk_index=idx,
                total_chunks=total_chunks,
                source_document_id=source_document_id,
                source=source,
                original_metadata=metadata,
                chunk_length=len(chunk_text)
            )
            
            documents.append(
                Document(
                    page_content=chunk_text,
                    metadata=chunk_metadata
                )
            )
        
        return documents
    
    def _build_chunk_metadata(
        self,
        document_id: str,
        chunk_id: str,
        chunk_index: int,
        total_chunks: int,
        source_document_id: Optional[int],
        source: str,
        original_metadata: Dict[str, Any],
        chunk_length: int
    ) -> Dict[str, Any]:
        """
        Build comprehensive metadata untuk chunk
        
        Metadata di-sanitize untuk kompatibilitas ChromaDB
        """
        metadata = {
            # ===== DOCUMENT TRACKING (KUNCI) =====
            "document_id": document_id,
            "chunk_id": chunk_id,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            
            # ===== SOURCE REFERENCE =====
            "source_document_id": source_document_id or 0,
            
            # ===== POSITION FLAGS =====
            "is_first_chunk": chunk_index == 0,
            "is_last_chunk": chunk_index == total_chunks - 1,
            
            # ===== NAVIGATION =====
            "prev_chunk_id": self._generate_chunk_id(document_id, chunk_index - 1) if chunk_index > 0 else "",
            "next_chunk_id": self._generate_chunk_id(document_id, chunk_index + 1) if chunk_index < total_chunks - 1 else "",
            
            # ===== SOURCE INFO =====
            "source": source,
            "filename": original_metadata.get("filename", source),
            
            # ===== DOMAIN METADATA =====
            "jenjang": original_metadata.get("jenjang", ""),
            "cabang": original_metadata.get("cabang", ""),
            "tahun": original_metadata.get("tahun", ""),
            "category": original_metadata.get("category", original_metadata.get("kategori", "")),
            
            # ===== CHUNK INFO =====
            "chunk_length": chunk_length,
            "chunk_strategy": self.strategy,
            "chunk_size_config": self._cfg.fixed_size["chunk_size"],
            "chunk_overlap_config": self._cfg.fixed_size["chunk_overlap"],
            "chunked_at": datetime.now().isoformat(),
        }
        
        # Merge additional metadata (sanitized)
        exclude_keys = set(metadata.keys())
        for key, value in original_metadata.items():
            if key not in exclude_keys:
                metadata[key] = self._sanitize_value(value)
        
        return metadata
    
    def _sanitize_value(self, value: Any) -> Any:
        """
        Sanitize value untuk kompatibilitas ChromaDB
        ChromaDB hanya support: str, int, float, bool
        """
        if value is None:
            return ""
        elif isinstance(value, bool):
            return value
        elif isinstance(value, (int, float)):
            return value
        elif isinstance(value, str):
            return value
        elif isinstance(value, list):
            return ", ".join(str(item) for item in value)
        elif isinstance(value, dict):
            return str(value)
        else:
            return str(value)
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    def get_statistics(self, documents: List[Document]) -> Dict[str, Any]:
        """Get chunking statistics"""
        if not documents:
            return {"total_chunks": 0, "total_documents": 0}
        
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
            
            lvl = doc.metadata.get("jenjang", "Unknown") or "Unknown"
            jenjang_dist[lvl] = jenjang_dist.get(lvl, 0) + 1
        
        return {
            "strategy": self.strategy,
            "config": {
                "chunk_size": self._cfg.fixed_size["chunk_size"],
                "chunk_overlap": self._cfg.fixed_size["chunk_overlap"]
            },
            "total_chunks": len(documents),
            "total_documents": len(docs_by_id),
            "avg_chunk_length": int(sum(lengths) / len(lengths)),
            "min_chunk_length": min(lengths),
            "max_chunk_length": max(lengths),
            "total_characters": sum(lengths),
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
    
    Menggabungkan:
    - EnhancedChunker untuk chunking
    - MetadataExtractor untuk metadata extraction
    """
    
    def __init__(
        self, 
        chunker: EnhancedChunker, 
        metadata_extractor=None
    ):
        """
        Initialize processor
        
        Args:
            chunker: EnhancedChunker instance
            metadata_extractor: MetadataExtractor instance (optional)
        """
        self.chunker = chunker
        self.metadata_extractor = metadata_extractor
    
    def process_document(
        self,
        filename: str,
        content: str,
        metadata: Dict[str, Any] = None,
        source_document_id: int = None
    ) -> List[Document]:
        """
        Process single document
        
        Args:
            filename: Nama file
            content: Konten dokumen
            metadata: Metadata (optional, akan di-extract jika tidak ada)
            source_document_id: ID dari table documents
        
        Returns:
            List of Document chunks
        """
        print(f"\n📄 Processing: {filename}")
        
        # Build metadata
        if metadata is None:
            metadata = {}
        
        # Extract metadata jika tidak ada dan extractor tersedia
        if self.metadata_extractor and not any([
            metadata.get("jenjang"),
            metadata.get("cabang"),
            metadata.get("tahun")
        ]):
            extracted = self.metadata_extractor.extract_full(filename, content)
            metadata = {**extracted, **metadata}  # Merge, keeping explicit metadata
            print("   🔍 Metadata extracted automatically")
        
        # Ensure source and filename
        metadata["source"] = metadata.get("source", filename)
        metadata["filename"] = filename
        
        # Chunk document
        chunks = self.chunker.chunk_document(
            content=content,
            metadata=metadata,
            source_document_id=source_document_id
        )
        
        print(f"   ✂️  Created {len(chunks)} chunks")
        if chunks:
            print(f"   🔑 Document ID: {chunks[0].metadata['document_id']}")
        
        return chunks
    
    def process_multiple_documents(
        self,
        documents: List[Dict[str, Any]]
    ) -> List[Document]:
        """
        Process multiple documents
        
        Args:
            documents: List of dict dengan keys:
                - filename: str
                - content: str
                - metadata: dict (optional)
                - source_document_id: int (optional)
        
        Returns:
            List of all Document chunks
        """
        all_chunks: List[Document] = []
        
        for doc in documents:
            chunks = self.process_document(
                filename=doc.get("filename", "unknown.pdf"),
                content=doc.get("content", ""),
                metadata=doc.get("metadata", {}),
                source_document_id=doc.get("source_document_id")
            )
            all_chunks.extend(chunks)
        
        # Print statistics
        if all_chunks:
            stats = self.chunker.get_statistics(all_chunks)
            print(f"\n📊 Processing Summary:")
            print(f"   Total chunks: {stats['total_chunks']}")
            print(f"   Total documents: {stats['total_documents']}")
            print(f"   Avg chunk length: {stats['avg_chunk_length']} chars")
        
        return all_chunks