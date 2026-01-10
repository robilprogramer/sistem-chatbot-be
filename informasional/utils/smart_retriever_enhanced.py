# utils/smart_retriever_enhanced.py

"""
Enhanced Smart Retriever with:
- Query processing integration
- Hybrid search (semantic + keyword)
- Metadata filtering
- Re-ranking
- Fallback mechanisms
"""

from typing import List, Dict, Optional
from langchain_core.documents import Document
from langchain_chroma import Chroma


class EnhancedSmartRetriever:
    """
    Enhanced Smart Retriever yang integrates dengan QueryProcessor
    
    Features:
    - Automatic metadata filtering from query
    - Hybrid retrieval (dense + sparse)
    - Context-aware re-ranking
    - Intelligent fallback
    - Result diversity
    """
    
    def __init__(
        self,
        vectorstore: Chroma,
        query_processor,
        top_k: int = 5,
        use_hybrid: bool = False,
        enable_reranking: bool = True,
        diversity_threshold: float = 0.7
    ):
        """
        Args:
            vectorstore: ChromaDB vectorstore
            query_processor: QueryProcessor instance
            top_k: Number of documents to retrieve
            use_hybrid: Enable hybrid search (semantic + BM25)
            enable_reranking: Enable re-ranking of results
            diversity_threshold: Min similarity for diversity filtering
        """
        self.vectorstore = vectorstore
        self.query_processor = query_processor
        self.top_k = top_k
        self.use_hybrid = use_hybrid
        self.enable_reranking = enable_reranking
        self.diversity_threshold = diversity_threshold
    
    def retrieve(
        self,
        query: str,
        manual_filters: Optional[Dict] = None,
        top_k: Optional[int] = None,
        conversation_history: Optional[List] = None
    ) -> List[Document]:
        """
        Main retrieval method with full pipeline
        
        Args:
            query: User question
            manual_filters: Override automatic filters
            top_k: Override default top_k
            conversation_history: Previous messages for context
            
        Returns:
            List of relevant documents
        """
        if top_k is None:
            top_k = self.top_k
        
        print(f"\n🔍 Enhanced Smart Retrieval")
        print(f"   Query: {query}")
        
        # 1. Process query
        processed = self.query_processor.process(query, conversation_history)
        
        # 2. Use manual filters or auto-extracted filters
        filters = manual_filters if manual_filters else processed.metadata_filters
        
        # 3. Prepare search query (use rewritten for better retrieval)
        search_query = processed.rewritten_query
        
        print(f"   Search Query: {search_query}")
        print(f"   Filters: {filters}")
        print(f"   Intent: {processed.intent}")
        
        # 4. Retrieve with filters
        docs = self._retrieve_with_strategy(
            search_query=search_query,
            filters=filters,
            top_k=top_k,
            keywords=processed.search_keywords
        )
        
        # 5. Re-rank if enabled
        if self.enable_reranking and len(docs) > 1:
            docs = self._rerank_documents(docs, query)
        
        # 6. Ensure diversity
        docs = self._ensure_diversity(docs)
        
        # 7. Limit to top_k
        docs = docs[:top_k]
        
        print(f"   ✅ Retrieved {len(docs)} documents")
        
        # Print metadata summary
        if docs:
            print(f"   📊 Results:")
            for i, doc in enumerate(docs[:3], 1):
                meta = doc.metadata
                print(f"      {i}. {meta.get('jenjang', '?')} | "
                      f"{meta.get('cabang', '?')} | "
                      f"{meta.get('tahun', '?')} | "
                      f"{meta.get('kategori', '?')}")
        
        return docs
    
    def _retrieve_with_strategy(
        self,
        search_query: str,
        filters: Optional[Dict],
        top_k: int,
        keywords: List[str]
    ) -> List[Document]:
        """
        Retrieve using multi-strategy approach
        
        Strategy:
        1. Try with filters first
        2. If results < threshold, try without filters
        3. Merge results intelligently
        """
        all_docs = []
        
        # Strategy 1: Semantic search with filters
        if filters:
            print(f"   📌 Strategy 1: Semantic + Filters")
            filtered_docs = self._semantic_search_with_filter(
                search_query, 
                filters, 
                top_k * 2  # Get more for ranking
            )
            all_docs.extend(filtered_docs)
            print(f"      → {len(filtered_docs)} docs")
        
        # Strategy 2: If not enough results, try without filters
        if len(all_docs) < top_k:
            print(f"   📌 Strategy 2: Semantic without filters")
            unfiltered_docs = self._semantic_search_no_filter(
                search_query,
                top_k * 2
            )
            
            # Add only new docs (not already in all_docs)
            existing_ids = {id(doc) for doc in all_docs}
            for doc in unfiltered_docs:
                if id(doc) not in existing_ids:
                    all_docs.append(doc)
            
            print(f"      → Added {len(all_docs) - len(filtered_docs if filters else [])} new docs")
        
        # Strategy 3: Keyword boost (if specific keywords detected)
        if keywords and len(all_docs) < top_k:
            print(f"   📌 Strategy 3: Keyword search")
            keyword_docs = self._keyword_search(keywords, filters, top_k)
            
            existing_ids = {id(doc) for doc in all_docs}
            for doc in keyword_docs:
                if id(doc) not in existing_ids:
                    all_docs.append(doc)
            
            print(f"      → Total now: {len(all_docs)} docs")
        
        return all_docs
    
    def _semantic_search_with_filter(
        self,
        query: str,
        filters: Dict,
        k: int
    ) -> List[Document]:
        """
        Semantic search with metadata filtering
        """
        print(f"   🔍 Semantic search with query: {query}")
        try:
            # Convert filters to Chroma where clause
            where_clause = self._build_where_clause(filters)
            
            if not where_clause:
                return []
            
            docs = self.vectorstore.similarity_search(
                query,
                k=k,
                filter=where_clause
            )
            
            return docs
            
        except Exception as e:
            print(f"      ⚠️ Filtered search error: {e}")
            return []
    
    def _semantic_search_no_filter(
        self,
        query: str,
        k: int
    ) -> List[Document]:
        """
        Semantic search without filtering
        """
        try:
            return self.vectorstore.similarity_search(query, k=k)
        except Exception as e:
            print(f"      ⚠️ Unfiltered search error: {e}")
            return []
    
    def _keyword_search(
        self,
        keywords: List[str],
        filters: Optional[Dict],
        k: int
    ) -> List[Document]:
        """
        Keyword-based search for specific terms
        """
        try:
            # Build keyword query
            keyword_query = " ".join(keywords)
            
            where_clause = None
            if filters:
                where_clause = self._build_where_clause(filters)
            
            docs = self.vectorstore.similarity_search(
                keyword_query,
                k=k,
                filter=where_clause
            )
            
            return docs
            
        except Exception as e:
            print(f"      ⚠️ Keyword search error: {e}")
            return []
    
    def _build_where_clause(self, filters: Dict) -> Optional[Dict]:
        """
        Build Chroma where clause from filters
        
        Handles both single and multiple filters correctly
        """
        if not filters:
            return None
        
        conditions = []
        
        for key, value in filters.items():
            if value:  # Only add non-empty values
                conditions.append({key: {"$eq": value}})
        
        if not conditions:
            return None
        
        # If only one condition, return it directly
        if len(conditions) == 1:
            return conditions[0]
        
        # Multiple conditions, use $and
        return {"$and": conditions}
    
    def _rerank_documents(
        self,
        docs: List[Document],
        query: str
    ) -> List[Document]:
        """
        Re-rank documents based on relevance
        
        Simple scoring based on:
        1. Keyword presence
        2. Metadata match
        3. Content length (prefer detailed answers)
        """
        print(f"   🔄 Re-ranking {len(docs)} documents...")
        
        scored_docs = []
        
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        for doc in docs:
            score = 0.0
            content_lower = doc.page_content.lower()
            
            # 1. Keyword matching (40%)
            content_words = set(content_lower.split())
            matching_words = query_words.intersection(content_words)
            keyword_score = len(matching_words) / len(query_words) if query_words else 0
            score += keyword_score * 0.4
            
            # 2. Metadata relevance (30%)
            meta = doc.metadata
            meta_score = 0
            if meta.get('jenjang'):
                meta_score += 0.3
            if meta.get('cabang'):
                meta_score += 0.3
            if meta.get('tahun'):
                meta_score += 0.2
            if meta.get('kategori'):
                meta_score += 0.2
            score += meta_score * 0.3
            
            # 3. Content completeness (30%)
            content_length = len(doc.page_content)
            # Prefer 500-2000 chars (not too short, not too long)
            if 500 <= content_length <= 2000:
                length_score = 1.0
            elif content_length < 500:
                length_score = content_length / 500
            else:
                length_score = 2000 / content_length
            score += length_score * 0.3
            
            scored_docs.append((score, doc))
        
        # Sort by score descending
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        
        # Return sorted docs
        reranked = [doc for score, doc in scored_docs]
        
        print(f"      Top scores: {[f'{s:.2f}' for s, _ in scored_docs[:3]]}")
        
        return reranked
    
    def _ensure_diversity(self, docs: List[Document]) -> List[Document]:
        """
        Ensure diversity in results
        Remove near-duplicate documents
        """
        if len(docs) <= 1:
            return docs
        
        diverse_docs = [docs[0]]  # Always include top result
        
        for doc in docs[1:]:
            # Check similarity with already selected docs
            is_diverse = True
            
            for selected in diverse_docs:
                # Simple diversity check: different metadata or different content
                if self._are_similar(doc, selected):
                    is_diverse = False
                    break
            
            if is_diverse:
                diverse_docs.append(doc)
        
        if len(diverse_docs) < len(docs):
            print(f"   🎯 Diversity filter: {len(docs)} → {len(diverse_docs)} docs")
        
        return diverse_docs
    
    def _are_similar(self, doc1: Document, doc2: Document) -> bool:
        """
        Check if two documents are too similar
        """
        # Check metadata
        meta1 = doc1.metadata
        meta2 = doc2.metadata
        
        # Same source = similar
        if (meta1.get('source') and meta2.get('source') and 
            meta1['source'] == meta2['source']):
            return True
        
        # Check content overlap
        content1 = set(doc1.page_content.lower().split())
        content2 = set(doc2.page_content.lower().split())
        
        if not content1 or not content2:
            return False
        
        overlap = len(content1.intersection(content2))
        smaller = min(len(content1), len(content2))
        
        similarity = overlap / smaller if smaller > 0 else 0
        
        # If >70% similar, consider as duplicate
        return similarity > self.diversity_threshold
    
    def retrieve_by_metadata(
        self,
        jenjang: Optional[str] = None,
        cabang: Optional[str] = None,
        tahun: Optional[str] = None,
        kategori: Optional[str] = None,
        limit: int = 10
    ) -> List[Document]:
        """
        Retrieve documents purely by metadata
        Useful for browsing/filtering
        """
        filters = {}
        
        if jenjang:
            filters['jenjang'] = jenjang
        if cabang:
            filters['cabang'] = cabang
        if tahun:
            filters['tahun'] = tahun
        if kategori:
            filters['kategori'] = kategori
        
        if not filters:
            print("⚠️ No metadata filters provided")
            return []
        
        where_clause = self._build_where_clause(filters)
        
        try:
            results = self.vectorstore._collection.get(
                where=where_clause,
                limit=limit,
                include=["documents", "metadatas"]
            )
            
            if not results or not results.get('documents'):
                return []
            
            docs = []
            for content, metadata in zip(results['documents'], results['metadatas']):
                doc = Document(page_content=content, metadata=metadata)
                docs.append(doc)
            
            return docs
            
        except Exception as e:
            print(f"⚠️ Metadata retrieval error: {e}")
            return []
    
    def get_available_metadata(self) -> Dict[str, List[str]]:
        """
        Get all unique metadata values
        Useful for UI filters
        """
        try:
            all_data = self.vectorstore._collection.get(
                include=["metadatas"],
                limit=10000  # Get all
            )
            
            if not all_data or not all_data.get('metadatas'):
                return {}
            
            # Collect unique values
            metadata_values = {
                'jenjang': set(),
                'cabang': set(),
                'tahun': set(),
                'kategori': set()
            }
            
            for meta in all_data['metadatas']:
                if meta:
                    for key in metadata_values.keys():
                        if meta.get(key):
                            metadata_values[key].add(meta[key])
            
            # Convert sets to sorted lists
            return {
                key: sorted(list(values)) 
                for key, values in metadata_values.items()
            }
            
        except Exception as e:
            print(f"⚠️ Error getting metadata: {e}")
            return {}
