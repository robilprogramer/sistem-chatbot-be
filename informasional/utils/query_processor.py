# utils/query_processor.py

from typing import Dict, Optional, List
import re
from dataclasses import dataclass
from openai import OpenAI

@dataclass
class ProcessedQuery:
    """Result from query processing"""
    original_query: str
    rewritten_query: str
    extracted_entities: Dict[str, str]
    search_keywords: List[str]
    metadata_filters: Dict[str, str]
    intent: str  # INFORMATIONAL, TRANSACTIONAL, NAVIGATIONAL


class QueryProcessor:
    """
    Advanced query processing with:
    - Entity extraction (jenjang, cabang, tahun, topic)
    - Query rewriting for better retrieval
    - Intent classification
    - Metadata filter extraction
    - Conversation context integration
    """
    
    def __init__(self, master_repo, llm=None):
        """
        Args:
            master_repo: Repository for getting jenjang, cabang lists
            llm: Optional LLM for advanced query rewriting
        """
        self.master_repo = master_repo
        self.llm = llm
        
        # Get master data
        self.jenjang_list = master_repo.get_jenjang()
        self.cabang_list = master_repo.get_cabang()
        self.kategori_list = master_repo.get_kategori()
    
    def process(
        self, 
        query: str, 
        conversation_history: Optional[List[Dict]] = None
    ) -> ProcessedQuery:
        """
        Main processing function
        
        Args:
            query: User question
            conversation_history: Previous messages for context
            
        Returns:
            ProcessedQuery with all extracted information
        """
        print(f"\n🔍 Processing Query: {query}")
        
        # 1. Extract entities
        entities = self._extract_entities(query)
        print(f"   Entities: {entities}")
        
        # 2. Extract metadata filters
        filters = self._extract_metadata_filters(query, entities)
        print(f"   Filters: {filters}")
        
        # 3. Classify intent
        intent = self._classify_intent(query)
        print(f"   Intent: {intent}")
        
        # 4. Extract keywords
        keywords = self._extract_keywords(query, entities)
        print(f"   Keywords: {keywords}")
        
        # 5. Rewrite query with context
        rewritten = self._rewrite_query(
            query, 
            entities, 
            filters, 
            conversation_history
        )
        print(f"   Rewritten: {rewritten}")
        
        return ProcessedQuery(
            original_query=query,
            rewritten_query=rewritten,
            extracted_entities=entities,
            search_keywords=keywords,
            metadata_filters=filters,
            intent=intent
        )
    
    def _extract_entities(self, query: str) -> Dict[str, str]:
        """
        Extract named entities from query
        
        Entities extracted:
        - jenjang: TK, SD, SMP, SMA, SMK
        - cabang: School branch
        - tahun: Year/academic year
        - topic: General topic (BIAYA, PENDAFTARAN, etc)
        """
        entities = {}
        query_lower = query.lower()
        
        # Extract jenjang
        for j in self.jenjang_list:
            pattern = rf'\b{re.escape(j.lower())}\b'
            if re.search(pattern, query_lower):
                entities['jenjang'] = j.upper()
                break
        
        # Extract cabang
        for c in self.cabang_list:
            # Normalize for matching
            c_normalized = c.lower().replace(" ", "")
            q_normalized = query_lower.replace(" ", "")
            
            if c_normalized in q_normalized or c.lower() in query_lower:
                entities['cabang'] = c.title()
                break
        
        # Extract tahun
        tahun_patterns = [
            r'20\d{2}/20\d{2}',  # 2024/2025
            r'20\d{2}-20\d{2}',  # 2024-2025
            r'tahun\s+20\d{2}',  # tahun 2024
            r'\b20\d{2}\b'       # 2024
        ]
        for pattern in tahun_patterns:
            match = re.search(pattern, query)
            if match:
                entities['tahun'] = match.group().replace('tahun ', '').strip()
                break
        
        # Extract topic keywords
        topic_map = {
            'BIAYA': ['biaya', 'spp', 'uang pangkal', 'tarif', 'iuran', 'bayar'],
            'PENDAFTARAN': ['daftar', 'pendaftaran', 'ppdb', 'pmb', 'registrasi'],
            'APLIKASI': ['aplikasi', 'app', 'salam', 'login', 'install'],
            'PEMBAYARAN': ['bayar', 'pembayaran', 'transfer', 'virtual account', 'va'],
            'LMS': ['lms', 'learning', 'e-learning', 'kuis', 'materi'],
            'BEASISWA': ['beasiswa', 'bantuan', 'keringanan'],
            'PROGRAM': ['tahfidz', 'bilingual', 'international', 'kelas']
        }
        
        for topic, keywords in topic_map.items():
            if any(kw in query_lower for kw in keywords):
                entities['topic'] = topic
                break
        
        return entities
    
    def _extract_metadata_filters(
        self, 
        query: str, 
        entities: Dict
    ) -> Dict[str, str]:
        """
        Convert entities to metadata filters for vector search
        """
        filters = {}
        
        if 'jenjang' in entities:
            filters['jenjang'] = entities['jenjang']
        
        if 'cabang' in entities:
            filters['cabang'] = entities['cabang']
        
        if 'tahun' in entities:
            filters['tahun'] = entities['tahun']
        
        # Map topic to kategori
        if 'topic' in entities:
            topic = entities['topic']
            
            # Direct mapping
            kategori_mapping = {
                'BIAYA': 'Biaya',
                'PENDAFTARAN': 'PPDB',
                'PEMBAYARAN': 'Pembayaran',
                'APLIKASI': 'Aplikasi',
                'LMS': 'LMS',
                'BEASISWA': 'Beasiswa',
                'PROGRAM': 'Program'
            }
            
            if topic in kategori_mapping:
                filters['kategori'] = kategori_mapping[topic]
        
        return filters
    
    def _classify_intent(self, query: str) -> str:
        """
        Classify user intent
        
        Returns:
            INFORMATIONAL: Asking for information
            TRANSACTIONAL: Want to do something (register, pay, etc)
            NAVIGATIONAL: Looking for link/location/contact
        """
        query_lower = query.lower()
        
        # Transactional keywords
        transactional_keywords = [
            'cara daftar', 'cara bayar', 'bagaimana daftar', 'bagaimana bayar',
            'daftar', 'bayar', 'upload', 'kirim', 'submit',
            'install', 'download', 'login'
        ]
        if any(kw in query_lower for kw in transactional_keywords):
            return "TRANSACTIONAL"
        
        # Navigational keywords
        navigational_keywords = [
            'link', 'alamat', 'lokasi', 'kontak', 'website', 
            'nomor', 'telepon', 'email', 'wa', 'whatsapp',
            'dimana', 'di mana'
        ]
        if any(kw in query_lower for kw in navigational_keywords):
            return "NAVIGATIONAL"
        
        # Default: informational
        return "INFORMATIONAL"
    
    def _extract_keywords(self, query: str, entities: Dict) -> List[str]:
        """
        Extract important keywords for search
        Remove stop words, keep meaningful terms
        """
        # Indonesian stop words
        stop_words = {
            'adalah', 'ada', 'apa', 'apakah', 'bagaimana', 'berapa',
            'di', 'untuk', 'yang', 'dari', 'ke', 'dan', 'atau',
            'pada', 'dengan', 'oleh', 'dalam', 'sebagai', 'akan',
            'saya', 'kami', 'kita', 'anda', 'bapak', 'ibu',
            'sudah', 'belum', 'tidak', 'bisa', 'dapat', 'harus',
            'ini', 'itu', 'tersebut', 'ya', 'tidak', 'mau', 'ingin'
        }
        
        # Tokenize and clean
        words = re.findall(r'\b\w+\b', query.lower())
        
        # Filter stop words and short words
        keywords = [
            w for w in words 
            if w not in stop_words and len(w) > 2
        ]
        
        # Add entity values as keywords
        for key, value in entities.items():
            if value and isinstance(value, str):
                keywords.append(value.lower())
        
        # Remove duplicates while preserving order
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)
        
        return unique_keywords
    
    def _rewrite_query(
        self,
        query: str,
        entities: Dict,
        filters: Dict,
        history: Optional[List[Dict]]
    ) -> str:
        """
        Rewrite query with context enrichment
        
        Strategies:
        1. Add entity context
        2. Add conversation context
        3. Expand with synonyms
        4. Make more specific
        """
        # Basic rewriting: add entity context
        enriched_parts = [query]
        
        # Add entity information
        if entities:
            entity_terms = []
            
            if 'jenjang' in entities:
                entity_terms.append(f"jenjang {entities['jenjang']}")
            
            if 'cabang' in entities:
                entity_terms.append(f"cabang {entities['cabang']}")
            
            if 'tahun' in entities:
                entity_terms.append(f"tahun {entities['tahun']}")
            
            if 'topic' in entities:
                entity_terms.append(entities['topic'].lower())
            
            if entity_terms:
                enriched_parts.append(" ".join(entity_terms))
        
        # Add conversation context (last message)
        if history and len(history) > 0:
            last_msg = history[-1]
            if isinstance(last_msg, dict) and 'content' in last_msg:
                # Extract key terms from last message
                last_content = last_msg['content'][:100]  # First 100 chars
                enriched_parts.append(f"[context: {last_content}]")
        
        return " ".join(enriched_parts)
    
    def rewrite_with_llm(
        self,
        query: str,
        entities: Dict,
        history: Optional[List[Dict]] = None
    ) -> str:
        """
        Advanced query rewriting using LLM
        Only use if self.llm is provided
        """
        if not self.llm:
            return query
        
        # Prepare context
        context_parts = []
        
        if entities:
            context_parts.append(f"Entities detected: {entities}")
        
        if history:
            recent_history = history[-3:]  # Last 3 messages
            context_parts.append("Recent conversation:")
            for msg in recent_history:
                role = msg.get('role', 'user')
                content = msg.get('content', '')[:100]
                context_parts.append(f"  {role}: {content}")
        
        context = "\n".join(context_parts)
        
        # Prompt for LLM
        prompt = f"""Rewrite the following user query to be more specific and searchable for a document retrieval system.

ORIGINAL QUERY: {query}

CONTEXT:
{context}

INSTRUCTIONS:
- Make the query more specific
- Add relevant context
- Expand abbreviations
- Keep it concise (max 2-3 sentences)

REWRITTEN QUERY:"""

        try:
            response = self.llm.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            print(f"⚠️ LLM rewriting failed: {e}")
            return query
