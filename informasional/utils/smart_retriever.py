# ============================================================================
# FILE: informasional/utils/smart_retriever.py
# ============================================================================
"""
Smart Retriever dengan Document Aggregation

FLOW:
1. User query → embed query
2. Search ChromaDB → get top-K chunks
3. Extract unique document_ids
4. Fetch ALL chunks untuk setiap document_id
5. Sort by chunk_index
6. Merge chunks → dokumen lengkap
7. Return context ke LLM

Ini menyelesaikan masalah "informasi terpotong"!
"""

from typing import List, Dict, Any
from collections import defaultdict
import numpy as np
from langchain_core.documents import Document
from langchain_chroma import Chroma


class SmartRetriever:
    """
    Smart Retriever dengan Document Aggregation
    
    KUNCI: Menggabungkan semua chunks dari dokumen yang sama
    sehingga context yang diberikan ke LLM menjadi lengkap.
    """
    
    def __init__(
        self,
        vectorstore: Chroma,
        embedding_function,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
        max_documents: int = 3,
        fetch_full_document: bool = True,
    ):
        """
        Args:
            vectorstore: ChromaDB vectorstore
            embedding_function: Embedding model
            top_k: Jumlah chunks awal yang di-retrieve
            similarity_threshold: Minimum similarity score (0-1)
            max_documents: Max dokumen unik yang diambil
            fetch_full_document: Jika True, fetch semua chunks per dokumen
        """
        self.vectorstore = vectorstore
        self.embedding_function = embedding_function
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        self.max_documents = max_documents
        self.fetch_full_document = fetch_full_document
        self.collection = vectorstore._collection
    
    def retrieve(self, query: str, verbose: bool = False) -> List[Document]:
        """
        Retrieve dan aggregate documents
        
        Args:
            query: User query
            verbose: Print debug info
        
        Returns:
            List[Document] dengan chunks yang sudah digabungkan per dokumen
        """
        if verbose:
            print(f"\n{'='*60}")
            print("🔍 SMART RETRIEVAL PIPELINE")
            print(f"{'='*60}")
            print(f"📝 Query: '{query}'")
        
        # 1️⃣ Embed query
        query_embedding = self.embedding_function.embed_query(query)
        
        # 2️⃣ Search top-K
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=self.top_k,
            include=["documents", "metadatas", "distances"]
        )
        
        if not results['ids'][0]:
            if verbose:
                print("❌ No results found")
            return []
        
        # 3️⃣ Process results
        relevant_docs = self._process_results(results, verbose)
        
        if not relevant_docs:
            return []
        
        # 4️⃣ Aggregate by document_id
        if self.fetch_full_document:
            aggregated = self._aggregate_by_document(relevant_docs, verbose)
            return aggregated
        else:
            return relevant_docs
    
    def _process_results(self, results: Dict, verbose: bool) -> List[Document]:
        """Process initial query results"""
        docs = []
        seen = set()
        
        for i, (doc_id, distance, content, metadata) in enumerate(zip(
            results['ids'][0],
            results['distances'][0],
            results['documents'][0],
            results['metadatas'][0]
        )):
            # Convert distance to similarity (cosine)
            similarity = 1 - (distance / 2)
            
            if similarity < self.similarity_threshold:
                if verbose:
                    print(f"   ⏭️ Skipping (score {similarity:.3f} < threshold)")
                continue
            
            chunk_id = metadata.get('chunk_id', doc_id)
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            
            metadata['similarity_score'] = similarity
            metadata['retrieval_rank'] = i + 1
            
            docs.append(Document(
                page_content=content,
                metadata=metadata
            ))
            
            if verbose:
                print(f"\n   {i+1}. [Score: {similarity:.3f}]")
                print(f"      Document ID: {metadata.get('document_id', 'N/A')}")
                print(f"      Chunk: {metadata.get('chunk_index', '?')}/{metadata.get('total_chunks', '?')}")
                print(f"      Preview: {content[:80]}...")
        
        if verbose:
            print(f"\n✅ Found {len(docs)} relevant chunks")
        
        return docs
    
    def _aggregate_by_document(
        self,
        initial_docs: List[Document],
        verbose: bool
    ) -> List[Document]:
        """
        🔑 KUNCI: Fetch ALL chunks dari dokumen yang sama
        """
        # Group by document_id
        docs_by_id: Dict[str, List[Document]] = defaultdict(list)
        doc_scores: Dict[str, float] = {}
        
        for doc in initial_docs:
            doc_id = doc.metadata.get('document_id')
            if not doc_id:
                doc_id = doc.metadata.get('source', 'unknown')
            
            docs_by_id[doc_id].append(doc)
            
            score = doc.metadata.get('similarity_score', 0)
            if doc_id not in doc_scores or score > doc_scores[doc_id]:
                doc_scores[doc_id] = score
        
        # Sort by score, limit to max_documents
        sorted_doc_ids = sorted(
            docs_by_id.keys(),
            key=lambda x: doc_scores.get(x, 0),
            reverse=True
        )[:self.max_documents]
        
        if verbose:
            print(f"\n📚 Aggregating {len(sorted_doc_ids)} documents")
        
        # Fetch ALL chunks for each document
        aggregated: List[Document] = []
        
        for doc_id in sorted_doc_ids:
            if verbose:
                print(f"\n   🔄 Fetching all chunks for: {doc_id}")
            
            # Query ChromaDB untuk semua chunks dengan document_id ini
            all_chunks = self._fetch_all_chunks(doc_id)
            
            if all_chunks:
                merged = self._merge_chunks(all_chunks, doc_scores.get(doc_id, 0))
                aggregated.append(merged)
                
                if verbose:
                    print(f"      ✅ Merged {len(all_chunks)} chunks → {len(merged.page_content)} chars")
        
        return aggregated
    
    def _fetch_all_chunks(self, document_id: str) -> List[Document]:
        """Fetch ALL chunks dengan document_id yang sama dari ChromaDB"""
        try:
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
            print(f"⚠️ Error fetching chunks for {document_id}: {e}")
            return []
    
    def _merge_chunks(
        self,
        chunks: List[Document],
        max_similarity: float
    ) -> Document:
        """Merge multiple chunks menjadi satu dokumen"""
        if not chunks:
            return None
        
        # Sort by chunk_index
        sorted_chunks = sorted(
            chunks,
            key=lambda x: x.metadata.get('chunk_index', 0)
        )
        
        # Combine content
        combined_content = "\n\n".join([
            c.page_content for c in sorted_chunks
        ])
        
        # Use first chunk metadata as base
        base_metadata = sorted_chunks[0].metadata.copy()
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
        """Get collection info"""
        count = self.collection.count()
        
        doc_ids = set()
        if count > 0:
            try:
                all_results = self.collection.get(include=["metadatas"])
                for meta in all_results.get('metadatas', []):
                    if meta and 'document_id' in meta:
                        doc_ids.add(meta['document_id'])
            except:
                pass
        
        return {
            "total_chunks": count,
            "unique_documents": len(doc_ids),
            "document_ids": list(doc_ids)[:20]
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
    
    def query(self, question: str, verbose: bool = False) -> Dict[str, Any]:
        """Execute RAG query"""
        if verbose:
            print(f"\n🚀 RAG PIPELINE")
            print(f"❓ Question: {question}")
        
        # Retrieve (dengan aggregation)
        docs = self.retriever.retrieve(question, verbose=verbose)
        
        if not docs:
            return {
                'answer': "Maaf, saya tidak menemukan informasi yang relevan dalam database.",
                'sources': [],
                'metadata': {
                    'num_sources': 0,
                    'relevance_check': 'FAILED - No relevant docs'
                }
            }
        
        # Check similarity
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
            print(f"\n📝 Context: {len(context)} chars from {len(docs)} documents")
        
        # Generate answer
        full_prompt = f"{self.system_prompt}\n\n{self.query_prompt.format(question=question, context=context)}"
        answer = self.llm.invoke(full_prompt).content
        
        # Build response
        sources = [{
            'source': doc.metadata.get('source', 'Unknown'),
            'document_id': doc.metadata.get('document_id', 'Unknown'),
            'jenjang': doc.metadata.get('jenjang', ''),
            'tahun': doc.metadata.get('tahun', ''),
            'similarity': doc.metadata.get('similarity_score', 0),
            'merged_chunks': doc.metadata.get('merged_chunks', 1)
        } for doc in docs]
        
        return {
            'answer': answer,
            'sources': sources,
            'metadata': {
                'num_sources': len(sources),
                'avg_similarity': float(avg_similarity),
                'max_similarity': float(max(similarities)),
                'total_context_length': len(context),
                'relevance_check': 'PASSED'
            }
        }
    
    def _build_context(self, docs: List[Document]) -> str:
        """Build context dari aggregated documents"""
        parts = []
        
        for i, doc in enumerate(docs, 1):
            meta = doc.metadata
            
            header = [f"[Dokumen {i}]"]
            if meta.get('source'):
                header.append(f"Source: {meta['source']}")
            if meta.get('jenjang'):
                header.append(f"Jenjang: {meta['jenjang']}")
            if meta.get('tahun'):
                header.append(f"Tahun: {meta['tahun']}")
            if meta.get('similarity_score'):
                header.append(f"Relevance: {meta['similarity_score']:.1%}")
            if meta.get('merged_chunks', 1) > 1:
                header.append(f"({meta['merged_chunks']} chunks merged)")
            
            parts.append(f"{' | '.join(header)}\n{doc.page_content}")
        
        return "\n\n---\n\n".join(parts)