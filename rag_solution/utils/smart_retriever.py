# ============================================================================
# FILE: utils/smart_retriever.py
# ============================================================================
"""
Smart Retriever dengan Document Aggregation

KONSEP UTAMA:
1. Retrieve chunks yang relevan
2. Identifikasi dokumen unik berdasarkan document_id
3. Fetch ALL chunks dari dokumen yang sama
4. Gabungkan chunks secara berurutan
5. Build context yang komprehensif

Ini menyelesaikan masalah "informasi terpotong" karena kita
menggabungkan semua chunks dari dokumen yang sama.
"""

from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import numpy as np
from langchain_core.documents import Document
from langchain_chroma import Chroma


class SmartRetriever:
    """
    Smart Retriever dengan Document Aggregation
    
    Flow:
    1. Query → Get top-K relevant chunks
    2. Extract unique document_ids dari hasil
    3. Fetch ALL chunks untuk setiap document_id
    4. Sort chunks by chunk_index
    5. Merge chunks menjadi dokumen lengkap
    """
    
    def __init__(
        self,
        vectorstore: Chroma,
        embedding_function,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
        max_documents: int = 3,  # Max dokumen unik yang diambil
        fetch_full_document: bool = True,  # Ambil semua chunks dari dokumen
    ):
        self.vectorstore = vectorstore
        self.embedding_function = embedding_function
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        self.max_documents = max_documents
        self.fetch_full_document = fetch_full_document
        self.collection = vectorstore._collection
    
    def retrieve(self, query: str, verbose: bool = True) -> List[Document]:
        """
        Retrieve dan aggregate documents
        
        Returns:
            List[Document] dengan chunks yang sudah digabungkan per dokumen
        """
        if verbose:
            print(f"\n{'='*60}")
            print("🔍 SMART RETRIEVAL PIPELINE")
            print(f"{'='*60}")
        
        # Step 1: Query embedding
        cleaned_query = query.lower().strip()
        query_embedding = self.embedding_function.embed_query(cleaned_query)
        
        if verbose:
            print(f"📝 Query: '{cleaned_query}'")
        
        # Step 2: Get initial top-K results
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=self.top_k,
            include=["documents", "metadatas", "distances"]
        )
        
        if not results['ids'][0]:
            if verbose:
                print("❌ No results found")
            return []
        
        # Step 3: Process results dan extract document_ids
        relevant_docs = self._process_initial_results(results, verbose)
        
        if not relevant_docs:
            return []
        
        # Step 4: Aggregate chunks by document_id
        if self.fetch_full_document:
            aggregated_docs = self._aggregate_by_document(relevant_docs, verbose)
        else:
            aggregated_docs = relevant_docs
        
        return aggregated_docs
    
    def _process_initial_results(
        self,
        results: Dict,
        verbose: bool
    ) -> List[Document]:
        """Process hasil query awal"""
        
        docs = []
        seen_chunks = set()
        
        for i, (doc_id, distance, content, metadata) in enumerate(zip(
            results['ids'][0],
            results['distances'][0],
            results['documents'][0],
            results['metadatas'][0]
        )):
            # Convert distance ke similarity (cosine)
            similarity = 1 - (distance / 2)
            
            if similarity < self.similarity_threshold:
                continue
            
            chunk_id = metadata.get('chunk_id', doc_id)
            if chunk_id in seen_chunks:
                continue
            seen_chunks.add(chunk_id)
            
            # Add similarity score ke metadata
            metadata['similarity_score'] = similarity
            metadata['retrieval_rank'] = i + 1
            
            docs.append(Document(
                page_content=content,
                metadata=metadata
            ))
            
            if verbose:
                print(f"\n{i+1}. [Score: {similarity:.3f}]")
                print(f"   Document ID: {metadata.get('document_id', 'N/A')}")
                print(f"   Chunk: {metadata.get('chunk_index', '?')}/{metadata.get('total_chunks', '?')}")
                print(f"   Source: {metadata.get('source', 'Unknown')}")
                print(f"   Preview: {content[:80]}...")
        
        if verbose:
            print(f"\n✅ Initial retrieval: {len(docs)} relevant chunks")
        
        return docs
    
    def _aggregate_by_document(
        self,
        initial_docs: List[Document],
        verbose: bool
    ) -> List[Document]:
        """
        KUNCI: Fetch semua chunks dari dokumen yang sama
        lalu gabungkan secara berurutan
        """
        
        # Group by document_id
        docs_by_id: Dict[str, List[Document]] = defaultdict(list)
        doc_scores: Dict[str, float] = {}  # Track max score per document
        
        for doc in initial_docs:
            doc_id = doc.metadata.get('document_id')
            if not doc_id:
                # Fallback: gunakan source sebagai document_id
                doc_id = doc.metadata.get('source', 'unknown')
            
            docs_by_id[doc_id].append(doc)
            
            # Track highest score untuk ranking
            score = doc.metadata.get('similarity_score', 0)
            if doc_id not in doc_scores or score > doc_scores[doc_id]:
                doc_scores[doc_id] = score
        
        # Sort document_ids by score (highest first)
        sorted_doc_ids = sorted(
            docs_by_id.keys(),
            key=lambda x: doc_scores.get(x, 0),
            reverse=True
        )[:self.max_documents]
        
        if verbose:
            print(f"\n📚 Found {len(sorted_doc_ids)} unique documents")
        
        # Fetch ALL chunks untuk setiap document
        aggregated_docs: List[Document] = []
        
        for doc_id in sorted_doc_ids:
            if verbose:
                print(f"\n🔄 Fetching all chunks for: {doc_id}")
            
            # Query semua chunks dengan document_id yang sama
            all_chunks = self._fetch_all_chunks_for_document(doc_id)
            
            if all_chunks:
                # Merge chunks menjadi satu dokumen
                merged_doc = self._merge_chunks(all_chunks, doc_scores.get(doc_id, 0))
                aggregated_docs.append(merged_doc)
                
                if verbose:
                    print(f"   ✅ Merged {len(all_chunks)} chunks → {len(merged_doc.page_content)} chars")
        
        return aggregated_docs
    
    def _fetch_all_chunks_for_document(self, document_id: str) -> List[Document]:
        """
        Fetch SEMUA chunks yang memiliki document_id yang sama
        """
        try:
            # Query dengan filter metadata
            results = self.collection.get(
                where={"document_id": document_id},
                include=["documents", "metadatas"]
            )
            
            if not results['ids']:
                return []
            
            chunks = []
            for doc_id, content, metadata in zip(
                results['ids'],
                results['documents'],
                results['metadatas']
            ):
                chunks.append(Document(
                    page_content=content,
                    metadata=metadata
                ))
            
            # Sort by chunk_index
            chunks.sort(key=lambda x: x.metadata.get('chunk_index', 0))
            
            return chunks
            
        except Exception as e:
            print(f"⚠️ Error fetching chunks: {e}")
            return []
    
    def _merge_chunks(
        self,
        chunks: List[Document],
        max_similarity: float
    ) -> Document:
        """
        Merge multiple chunks menjadi satu dokumen
        """
        if not chunks:
            return None
        
        # Sort by chunk_index
        sorted_chunks = sorted(
            chunks,
            key=lambda x: x.metadata.get('chunk_index', 0)
        )
        
        # Combine content
        combined_content = "\n\n".join([
            chunk.page_content for chunk in sorted_chunks
        ])
        
        # Use metadata dari first chunk sebagai base
        base_metadata = sorted_chunks[0].metadata.copy()
        
        # Update dengan aggregation info
        base_metadata.update({
            'merged_chunks': len(sorted_chunks),
            'chunk_indices': [c.metadata.get('chunk_index', 0) for c in sorted_chunks],
            'similarity_score': max_similarity,
            'is_aggregated': True,
            'total_length': len(combined_content)
        })
        
        return Document(
            page_content=combined_content,
            metadata=base_metadata
        )
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Debug: Get info tentang collection"""
        count = self.collection.count()
        
        # Sample beberapa documents untuk melihat struktur
        sample = self.collection.peek(limit=5)
        
        # Get unique document_ids
        all_results = self.collection.get(include=["metadatas"])
        doc_ids = set()
        for meta in all_results.get('metadatas', []):
            if meta and 'document_id' in meta:
                doc_ids.add(meta['document_id'])
        
        return {
            "total_chunks": count,
            "unique_documents": len(doc_ids),
            "document_ids": list(doc_ids)[:10],  # Sample
            "sample_metadata": sample.get('metadatas', [])[:2] if sample else []
        }


# ============================================================================
# ENHANCED QUERY CHAIN
# ============================================================================
class EnhancedQueryChain:
    """
    Query Chain dengan context building yang optimal
    """
    
    def __init__(
        self,
        smart_retriever: SmartRetriever,
        llm,
        system_prompt: str,
        query_prompt: str
    ):
        self.retriever = smart_retriever
        self.llm = llm
        self.system_prompt = system_prompt
        self.query_prompt = query_prompt
    
    def query(self, question: str, verbose: bool = True) -> Dict[str, Any]:
        """
        Execute RAG query
        """
        if verbose:
            print(f"\n🚀 RAG PIPELINE START")
            print(f"❓ Question: {question}")
        
        # Retrieve aggregated documents
        docs = self.retriever.retrieve(question, verbose=verbose)
        
        if not docs:
            return {
                'answer': "Maaf, saya tidak menemukan informasi yang relevan dalam database.",
                'sources': [],
                'metadata': {
                    'num_sources': 0,
                    'avg_similarity': 0,
                    'relevance_check': 'FAILED - No relevant documents'
                }
            }
        
        # Check average similarity
        similarities = [doc.metadata.get('similarity_score', 0) for doc in docs]
        avg_similarity = np.mean(similarities)
        
        if avg_similarity < 0.5:
            return {
                'answer': "Maaf, saya tidak yakin dengan informasi yang ditemukan. Silakan coba pertanyaan yang lebih spesifik.",
                'sources': [],
                'metadata': {
                    'num_sources': len(docs),
                    'avg_similarity': float(avg_similarity),
                    'relevance_check': 'FAILED - Low similarity'
                }
            }
        
        # Build context
        context = self._build_context(docs)
        
        if verbose:
            print(f"\n📝 Context built: {len(context)} chars from {len(docs)} documents")
        
        # Build full prompt
        full_prompt = f"{self.system_prompt}\n\n{self.query_prompt.format(question=question, context=context)}"
        
        # Generate answer
        answer = self.llm.invoke(full_prompt).content
        
        # Build sources
        sources = []
        for doc in docs:
            sources.append({
                'source': doc.metadata.get('source', 'Unknown'),
                'document_id': doc.metadata.get('document_id', 'Unknown'),
                'jenjang': doc.metadata.get('jenjang', ''),
                'cabang': doc.metadata.get('cabang', ''),
                'tahun': doc.metadata.get('tahun', ''),
                'similarity': doc.metadata.get('similarity_score', 0),
                'merged_chunks': doc.metadata.get('merged_chunks', 1),
                'total_length': doc.metadata.get('total_length', len(doc.page_content))
            })
        
        return {
            'answer': answer,
            'sources': sources,
            'metadata': {
                'num_sources': len(sources),
                'avg_similarity': float(avg_similarity),
                'max_similarity': float(max(similarities)),
                'min_similarity': float(min(similarities)),
                'total_context_length': len(context),
                'relevance_check': 'PASSED'
            }
        }
    
    def _build_context(self, docs: List[Document]) -> str:
        """
        Build context dari aggregated documents
        
        Format:
        [Dokumen 1] Source: xxx | Jenjang: xxx | Tahun: xxx | Relevance: xx%
        <content>
        
        [Dokumen 2] ...
        """
        context_parts = []
        
        for i, doc in enumerate(docs, 1):
            meta = doc.metadata
            
            # Build header
            header_parts = [f"[Dokumen {i}]"]
            
            if meta.get('source'):
                header_parts.append(f"Source: {meta['source']}")
            if meta.get('jenjang'):
                header_parts.append(f"Jenjang: {meta['jenjang']}")
            if meta.get('cabang'):
                header_parts.append(f"Cabang: {meta['cabang']}")
            if meta.get('tahun'):
                header_parts.append(f"Tahun: {meta['tahun']}")
            if meta.get('similarity_score'):
                header_parts.append(f"Relevance: {meta['similarity_score']:.1%}")
            if meta.get('merged_chunks', 1) > 1:
                header_parts.append(f"({meta['merged_chunks']} chunks merged)")
            
            header = " | ".join(header_parts)
            
            context_parts.append(f"{header}\n{doc.page_content}")
        
        return "\n\n---\n\n".join(context_parts)


# ============================================================================
# QUICK TEST
# ============================================================================
if __name__ == "__main__":
    print("Smart Retriever module loaded successfully")
    print("Use with: from utils.smart_retriever import SmartRetriever, EnhancedQueryChain")
