# utils/enhanced_query_chain.py

"""
Enhanced Query Chain for RAG System
Integrates retrieval, LLM, and prompt engineering
"""

from typing import Dict, List, Optional, Any
from langchain_core.documents import Document


class EnhancedQueryChain:
    """
    Complete query chain with:
    - Smart retrieval
    - Conversation history
    - Context assembly
    - LLM generation
    - Source attribution
    """
    
    def __init__(
        self,
        smart_retriever,
        llm,
        system_prompt: str,
        query_prompt: str,
        conversation_prompt: Optional[str] = None
    ):
        """
        Args:
            smart_retriever: EnhancedSmartRetriever instance
            llm: Language model
            system_prompt: System-level instructions
            query_prompt: Query template (with {context} and {question})
            conversation_prompt: Optional template for conversation context
        """
        self.retriever = smart_retriever
        self.llm = llm
        self.system_prompt = system_prompt
        self.query_prompt = query_prompt
        self.conversation_prompt = conversation_prompt
    
    def query(
        self,
        question: str,
        filters: Optional[Dict] = None,
        conversation_history: Optional[List[Dict]] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute complete query pipeline
        
        Args:
            question: User question
            filters: Manual metadata filters
            conversation_history: Previous messages
            session_id: Session identifier
            
        Returns:
            Dict with answer, sources, metadata
        """
        print(f"\n{'='*60}")
        print(f"🤖 RAG Query Pipeline")
        print(f"{'='*60}")
        
        # 1. Retrieve relevant documents
        docs = self.retriever.retrieve(
            query=question,
            manual_filters=filters,
            conversation_history=conversation_history
        )
        
        # 2. Handle no results
        if not docs:
            return self._handle_no_results(question)
        
        # 3. Assemble context
        context, sources = self._assemble_context(docs)
        
        print(f"\n📝 Context assembled: {len(context)} chars from {len(sources)} sources")
        
        # 4. Build prompt
        prompt = self._build_prompt(
            question=question,
            context=context,
            conversation_history=conversation_history
        )
        
        # 5. Generate answer
        print(f"\n🔮 Generating answer...")
        answer = self._generate_answer(prompt)
        
        # 6. Post-process answer
        answer = self._post_process_answer(answer, sources)
        
        print(f"\n✅ Answer generated: {len(answer)} chars")
        print(f"{'='*60}\n")
        
        return {
            'answer': answer,
            'sources': sources,
            'metadata': {
                'num_sources': len(sources),
                'filters_used': filters,
                'session_id': session_id,
                'has_conversation_context': bool(conversation_history)
            }
        }
    
    def _assemble_context(
        self,
        docs: List[Document]
    ) -> tuple[str, List[Dict]]:
        """
        Assemble context from retrieved documents
        
        Returns:
            Tuple of (context_string, sources_list)
        """
        context_parts = []
        sources = []
        
        for i, doc in enumerate(docs, 1):
            meta = doc.metadata
            
            # Build metadata header
            meta_parts = [f"[Dokumen {i}]"]
            
            if meta.get('jenjang'):
                meta_parts.append(f"Jenjang: {meta['jenjang']}")
            
            if meta.get('cabang'):
                meta_parts.append(f"Cabang: {meta['cabang']}")
            
            if meta.get('tahun'):
                meta_parts.append(f"Tahun: {meta['tahun']}")
            
            if meta.get('kategori'):
                meta_parts.append(f"Kategori: {meta['kategori']}")
            
            meta_header = " | ".join(meta_parts)
            
            # Assemble context part
            context_part = f"{meta_header}\n{doc.page_content}"
            context_parts.append(context_part)
            
            # Track source
            sources.append({
                'source': meta.get('source', 'Unknown'),
                'jenjang': meta.get('jenjang', 'Unknown'),
                'cabang': meta.get('cabang', 'Unknown'),
                'tahun': meta.get('tahun', 'Unknown'),
                'kategori': meta.get('kategori', 'Unknown'),
                'content_preview': doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content
            })
        
        # Join with separator
        context = "\n\n" + "="*50 + "\n\n".join(context_parts)
        
        return context, sources
    
    def _build_prompt(
        self,
        question: str,
        context: str,
        conversation_history: Optional[List[Dict]] = None
    ) -> str:
        """
        Build complete prompt for LLM
        """
        # Start with system prompt
        full_prompt = self.system_prompt + "\n\n"
        
        # Add conversation history if exists
        if conversation_history and len(conversation_history) > 0:
            history_str = self._format_conversation_history(conversation_history)
            
            # Add conversation context section
            full_prompt += "RIWAYAT PERCAKAPAN:\n"
            full_prompt += history_str + "\n\n"
            full_prompt += """INSTRUKSI KONTEKS PERCAKAPAN:
- Perhatikan konteks percakapan sebelumnya
- Jika pertanyaan mereferensi percakapan sebelumnya, sambungkan konteksnya
- Maintain konsistensi dalam percakapan

"""
        
        # Add main query prompt
        full_prompt += self.query_prompt.format(
            context=context,
            question=question
        )
        
        return full_prompt
    
    def _format_conversation_history(
        self,
        history: List[Dict]
    ) -> str:
        """
        Format conversation history for prompt
        """
        formatted = []
        
        # Only use last N messages to avoid context overflow
        recent_history = history[-5:] if len(history) > 5 else history
        
        for msg in recent_history:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            
            if role == 'user':
                formatted.append(f"User: {content}")
            elif role == 'assistant':
                formatted.append(f"Assistant: {content}")
        
        return "\n".join(formatted)
    
    def _generate_answer(self, prompt: str) -> str:
        """
        Generate answer using LLM
        """
        try:
            response = self.llm.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            print(f"❌ LLM generation error: {e}")
            return "Maaf, terjadi kesalahan dalam memproses pertanyaan Anda. Silakan coba lagi."
    
    def _post_process_answer(
        self,
        answer: str,
        sources: List[Dict]
    ) -> str:
        """
        Post-process answer
        - Add source attribution if not present
        - Format cleanup
        """
        # Check if answer already has source attribution
        if "Sumber:" not in answer and sources:
            # Add source attribution
            source_lines = ["\n\n**Sumber Informasi:**"]
            
            # Group by kategori or jenjang
            seen = set()
            for src in sources:
                source_key = f"{src['jenjang']}_{src['cabang']}_{src['tahun']}"
                if source_key not in seen:
                    seen.add(source_key)
                    source_str = f"- {src['kategori']}"
                    if src['jenjang'] != 'Unknown':
                        source_str += f" {src['jenjang']}"
                    if src['cabang'] != 'Unknown':
                        source_str += f" {src['cabang']}"
                    if src['tahun'] != 'Unknown':
                        source_str += f" ({src['tahun']})"
                    
                    source_lines.append(source_str)
            
            if len(source_lines) > 1:
                answer += "\n".join(source_lines)
        
        return answer
    
    def _handle_no_results(self, question: str) -> Dict[str, Any]:
        """
        Handle case when no documents are retrieved
        """
        answer = """Maaf, saya tidak menemukan informasi yang relevan dalam database saya untuk pertanyaan Anda.

**Untuk mendapatkan informasi lebih lanjut, silakan hubungi:**

- **Tata Usaha (TU)** sekolah terkait
- **Call Center YPI Al-Azhar**: (021) XXX-XXXX
- **Website Resmi**: https://ypi-alazhar.or.id
- **Email**: info@ypi-alazhar.or.id

Mohon maaf atas ketidaknyamanannya. Tim kami akan terus memperbarui database untuk melayani Anda lebih baik."""

        return {
            'answer': answer,
            'sources': [],
            'metadata': {
                'num_sources': 0,
                'no_results': True
            }
        }


class ConversationManager:
    """
    Manage conversation history for multi-turn interactions
    """
    
    def __init__(self, max_history: int = 10):
        """
        Args:
            max_history: Maximum number of messages to keep
        """
        self.max_history = max_history
        self.sessions = {}  # session_id -> history
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str
    ):
        """
        Add message to conversation history
        
        Args:
            session_id: Session identifier
            role: 'user' or 'assistant'
            content: Message content
        """
        if session_id not in self.sessions:
            self.sessions[session_id] = []
        
        self.sessions[session_id].append({
            'role': role,
            'content': content
        })
        
        # Trim if exceeds max
        if len(self.sessions[session_id]) > self.max_history:
            self.sessions[session_id] = self.sessions[session_id][-self.max_history:]
    
    def get_history(self, session_id: str) -> List[Dict]:
        """
        Get conversation history for session
        """
        return self.sessions.get(session_id, [])
    
    def clear_session(self, session_id: str):
        """
        Clear conversation history for session
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
    
    def clear_all(self):
        """
        Clear all sessions
        """
        self.sessions = {}
