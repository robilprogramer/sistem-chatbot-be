
from typing import List, Dict
from langchain_core.documents import Document
from langchain_chroma import Chroma
import numpy as np


class SmartRetriever:
    def __init__(
        self,
        vectorstore: Chroma,
        embedding_function,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
        min_docs_required: int = 2  # ✅ Minimal 2 dokumen relevan
    ):
        self.vectorstore = vectorstore
        self.embedding_function = embedding_function
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        self.min_docs_required = min_docs_required
        self.collection = vectorstore._collection
    
    def retrieve(self, query: str) -> List[Document]:
        """
        Main retrieval flow:
        1. Preprocess query
        2. Embed query
        3. Search vector database
        4. Filter by similarity threshold
        5. Return documents
        """
        print(f"\n{'='*60}")
        print(f"🔍 RETRIEVAL PIPELINE")
        print(f"{'='*60}")
        
        # Step 1: Preprocess query
        cleaned_query = query.lower().strip()
        print(f"📝 Query: '{cleaned_query}'")
        
        # Step 2: Embed query
        query_embedding = self.embedding_function.embed_query(cleaned_query)
        print(f"🔢 Embedding dimension: {len(query_embedding)}")
        
        # Step 3: Search vector database
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=self.top_k,
            include=["documents", "metadatas", "distances"]
        )
        
        print(f"🎯 Searching for top {self.top_k} results")
        print(f"📊 Found {len(results['ids'][0])} relevant chunks")
        
        # Step 4: Process results and filter by similarity
        docs = []
        for i, (doc_id, distance, content, metadata) in enumerate(zip(
            results['ids'][0],
            results['distances'][0],
            results['documents'][0],
            results['metadatas'][0]
        )):
            # Convert distance to similarity
            similarity = 1 - (distance / 2)  # Normalize cosine distance
            
            # Filter by threshold
            if similarity >= self.similarity_threshold:
                # Add similarity to metadata
                metadata['similarity_score'] = similarity
                
                # Create Document
                doc = Document(
                    page_content=content,
                    metadata=metadata
                )
                docs.append(doc)
                
                # Print info
                print(f"\n{i+1}. [{similarity:.3f}] "
                      f"{metadata.get('jenjang', '?')} - "
                      f"{metadata.get('tahun', '?')}")
                print(f"   Content preview: {content[:100]}...")
        
        # # ✅ Check if enough relevant docs
        # if len(docs) < self.min_docs_required:
        #     print(f"\n⚠️ WARNING: Only {len(docs)} docs above threshold {self.similarity_threshold}")
        #     print(f"   Required: {self.min_docs_required}")
        #     print(f"   → Returning empty (will trigger 'tidak menemukan' response)")
        #     return []
        
        print(f"\n✅ Filtered to {len(docs)} documents (threshold: {self.similarity_threshold})")
        return docs


# ============================================================================
# ENHANCED QUERY CHAIN - SIMPLIFIED
# ============================================================================

class EnhancedQueryChain:
    """
    Simplified query chain
    
    Flow:
    1. Retrieve documents (embedding search)
    2. Augment prompt with context
    3. Generate response
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
    
    def query(self, question: str) -> Dict:
        print(f"\n{'='*60}")
        print(f"🚀 RAG PIPELINE START")
        print(f"{'='*60}")
        print(f"❓ Question: {question}")
        
        # Retrieve documents
        docs = self.retriever.retrieve(question)
        
        # ✅ Jika tidak ada dokumen relevan
        if not docs:
            print(f"\n⚠️ NO RELEVANT DOCUMENTS FOUND")
            return {
                'answer': "Maaf, saya tidak menemukan informasi yang relevan tentang pertanyaan Anda dalam database. Silakan hubungi customer service untuk informasi lebih lanjut.",
                'sources': [],
                'metadata': {
                    'num_sources': 0,
                    'avg_similarity': 0,
                    'relevance_check': 'FAILED - No relevant docs'
                }
            }
        
        # ✅ Check average similarity
        avg_similarity = np.mean([doc.metadata['similarity_score'] for doc in docs])
        
        if avg_similarity < 0.6:
            print(f"\n⚠️ LOW AVERAGE SIMILARITY: {avg_similarity:.3f}")
            return {
                'answer': "Maaf, saya tidak yakin dengan informasi yang ditemukan. Silakan verifikasi langsung dengan customer service.",
                'sources': [],
                'metadata': {
                    'num_sources': len(docs),
                    'avg_similarity': avg_similarity,
                    'relevance_check': 'FAILED - Low similarity'
                }
            }
        
        # Build context & generate response
        context = self._build_context(docs)
        
        print(f"\n📝 CONTEXT BUILT:")
        print(f"   Sources: {len(docs)}")
        print(f"   Avg Similarity: {avg_similarity:.3f}")
        print(f"   Context length: {len(context)} chars")
        
        # Generate response
        full_prompt = f"""{self.system_prompt}

{self.query_prompt.format(question=question, context=context)}"""
        
        print(f"\n🤖 GENERATING RESPONSE...")
        answer = self.llm.invoke(full_prompt).content
        
        # Prepare sources
        sources = [
            {
                'source': doc.metadata.get('source', 'Unknown'),
                'jenjang': doc.metadata.get('jenjang', 'Unknown'),
                'cabang': doc.metadata.get('cabang', 'Unknown'),
                'tahun': doc.metadata.get('tahun', 'Unknown'),
                'similarity': doc.metadata.get('similarity_score', 0)
            }
            for doc in docs
        ]
        
        print(f"\n✅ RESPONSE GENERATED")
        print(f"{'='*60}\n")
        
        return {
            'answer': answer,
            'sources': sources,
            'metadata': {
                'num_sources': len(sources),
                'avg_similarity': avg_similarity,
                'max_similarity': max([s['similarity'] for s in sources]),
                'min_similarity': min([s['similarity'] for s in sources]),
                'relevance_check': 'PASSED'
            }
        }
    
    def _build_context(self, docs: List[Document]) -> str:
        """Build context string from documents"""
        context_parts = []
        
        for i, doc in enumerate(docs):
            meta = doc.metadata
            
            # Format metadata
            meta_info = f"[Dokumen {i+1}]"
            if meta.get('jenjang'):
                meta_info += f" Jenjang: {meta['jenjang']}"
            if meta.get('cabang'):
                meta_info += f" | Cabang: {meta['cabang']}"
            if meta.get('tahun'):
                meta_info += f" | Tahun: {meta['tahun']}"
            if meta.get('similarity_score'):
                meta_info += f" | Relevance: {meta['similarity_score']:.1%}"
            
            context_parts.append(f"{meta_info}\n{doc.page_content}")
        
        return "\n\n---\n\n".join(context_parts)