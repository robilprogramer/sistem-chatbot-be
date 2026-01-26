"""
RAG Performance Testing Script - Direct Module Access
======================================================
Script untuk mengukur performa RAG langsung dari modules:
- SmartRetriever (informasional/utils/smart_retriever.py)
- QueryChain (informasional/core/rag_factory.py)

Output: Markdown report dengan tabel hasil pengujian

USAGE:
    python rag_performance_test_direct.py --config path/to/config.yaml
"""

import sys
import os
import time
import argparse
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime

# Add project root to path (sesuaikan dengan struktur project)
# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from informasional.utils.smart_retriever import get_smart_retriever, reset_smart_retriever
from informasional.core.rag_factory import get_query_chain, reset_query_chain


# ============================================================================
# CONFIGURATION
# ============================================================================

# Default config path
DEFAULT_CONFIG_PATH = "informasional/config/config.yaml"

# Query untuk pengujian Retrieval Accuracy (5 query sesuai tabel)
RETRIEVAL_QUERIES = [
    {
        "no": 1,
        "query": "Biaya Sekolah SD Al-Azhar Cibinong",
        "expected_keywords": ["biaya", "sd", "al-azhar", "Cibinong", "spp", "pendaftaran", "uang"],
        "filter": None  # atau {"jenjang": "SD"} jika ingin filter
    },
    {
        "no": 2,
        "query": "Persyaratan pendaftaran",
        "expected_keywords": ["persyaratan", "pendaftaran", "smp", "dokumen", "syarat", "daftar"],
        "filter": None
    },
    {
        "no": 3,
        "query": "Jadwal Pendaftaran",
        "expected_keywords": ["jadwal", "tahun", "ajaran", "kalender", "akademik", "semester"],
        "filter": None
    },
    {
        "no": 4,
        "query": "Fasilitas sekolah",
        "expected_keywords": ["fasilitas", "sekolah", "gedung", "ruang", "laboratorium", "sarana"],
        "filter": None
    },
    {
        "no": 5,
        "query": "Kurikulum yang digunakan",
        "expected_keywords": ["kurikulum", "merdeka", "k13", "pembelajaran", "mata", "pelajaran"],
        "filter": None
    }
]

# Query untuk pengujian Response Quality (3 query sesuai tabel)
RESPONSE_QUERIES = [
    {
        "no": 1,
        "query": "Berapa biaya pendaftaran untuk SD Cibinong Al-Azhar?",
        "filter": None
    },
    {
        "no": 2,
        "query": "Apa saja dokumen yang diperlukan untuk mendaftar ke SD Al-Azhar?",
        "filter": None
    },
    {
        "no": 3,
        "query": "Jelaskan program unggulan yang ada di SMP Al-Azhar",
        "filter": None
    }
]


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class RetrievalResult:
    """Hasil pengujian retrieval accuracy"""
    no: int
    query: str
    retrieved_docs: int
    relevant_docs: int
    precision: float
    time_seconds: float
    doc_ids: List[str] = field(default_factory=list)
    similarity_scores: List[float] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class ResponseQualityResult:
    """Hasil pengujian response quality"""
    no: int
    query: str
    answer: str
    relevance: int  # 1-5
    accuracy: int   # 1-5
    completeness: int  # 1-5
    average: float
    sources_count: int
    avg_similarity: float = 0.0
    error: Optional[str] = None


# ============================================================================
# PRECISION CALCULATION
# ============================================================================

def calculate_precision(docs: List, expected_keywords: List[str]) -> tuple:
    """
    Hitung precision berdasarkan keyword matching
    
    Args:
        docs: List of Document objects dari retriever
        expected_keywords: Keywords yang diharapkan ada di dokumen relevan
    
    Returns:
        (relevant_count, precision)
    """
    if not docs:
        return 0, 0.0
    
    relevant_count = 0
    keywords_lower = [k.lower() for k in expected_keywords]
    
    for doc in docs:
        content = doc.page_content.lower()
        source = doc.metadata.get("source", "").lower()
        doc_id = doc.metadata.get("document_id", "").lower()
        
        # Gabungkan semua text untuk matching
        combined_text = f"{content} {source} {doc_id}"
        
        # Check if any keyword matches
        for keyword in keywords_lower:
            if keyword in combined_text:
                relevant_count += 1
                break
    
    precision = relevant_count / len(docs) if docs else 0.0
    return relevant_count, precision


# ============================================================================
# AUTO SCORING FOR RESPONSE QUALITY
# ============================================================================

def auto_score_response(
    query: str,
    answer: str,
    sources: List[Dict],
    metadata: Dict
) -> tuple:
    """
    Auto-scoring berdasarkan heuristics
    
    Kriteria:
    - Relevance: Berdasarkan similarity score
    - Accuracy: Berdasarkan relevance check dan sumber
    - Completeness: Berdasarkan panjang jawaban dan jumlah sumber
    
    Returns:
        (relevance, accuracy, completeness) - masing-masing 1-5
    """
    relevance = 3
    accuracy = 3
    completeness = 3
    
    # === RELEVANCE (berdasarkan similarity score) ===
    avg_similarity = metadata.get("avg_similarity", 0)
    if avg_similarity >= 0.8:
        relevance = 5
    elif avg_similarity >= 0.7:
        relevance = 4
    elif avg_similarity >= 0.6:
        relevance = 3
    elif avg_similarity >= 0.5:
        relevance = 2
    else:
        relevance = 1
    
    # === ACCURACY (berdasarkan relevance check) ===
    relevance_check = metadata.get("relevance_check", "")
    if "PASSED" in relevance_check:
        accuracy = 4
        if len(sources) >= 2:
            accuracy = 5
    elif "FAILED" in relevance_check:
        accuracy = 2
    
    # Check untuk jawaban default/tidak ditemukan
    answer_lower = answer.lower()
    if any(phrase in answer_lower for phrase in ["tidak ditemukan", "maaf", "tidak ada informasi"]):
        accuracy = max(1, accuracy - 2)
    
    # === COMPLETENESS (berdasarkan panjang dan sumber) ===
    answer_len = len(answer)
    num_sources = len(sources)
    
    if answer_len >= 500 and num_sources >= 2:
        completeness = 5
    elif answer_len >= 300 and num_sources >= 1:
        completeness = 4
    elif answer_len >= 150:
        completeness = 3
    elif answer_len >= 50:
        completeness = 2
    else:
        completeness = 1
    
    return relevance, accuracy, completeness


# ============================================================================
# RETRIEVAL ACCURACY TESTING
# ============================================================================

def run_retrieval_accuracy_tests(config_path: str) -> List[RetrievalResult]:
    """
    Jalankan pengujian Retrieval Accuracy menggunakan SmartRetriever langsung
    """
    results = []
    
    print("\n" + "="*60)
    print("📊 PENGUJIAN RETRIEVAL ACCURACY")
    print("="*60)
    
    # Get SmartRetriever singleton
    retriever = get_smart_retriever(config_path)
    
    print(f"\n📦 Collection Info:")
    info = retriever.get_collection_info()
    print(f"   └─ Total Vectors: {info.get('total_vectors', 0)}")
    print(f"   └─ Unique Documents: {info.get('unique_documents', 0)}")
    print(f"   └─ Embedding Model: {info.get('embedding_model', 'N/A')}")
    
    for query_config in RETRIEVAL_QUERIES:
        no = query_config["no"]
        query = query_config["query"]
        expected_keywords = query_config["expected_keywords"]
        filter_dict = query_config.get("filter")
        
        print(f"\n[{no}/5] Testing: \"{query}\"")
        
        try:
            # Measure time
            start_time = time.time()
            
            # Call retriever directly
            docs = retriever.retrieve(
                query=query,
                filter=filter_dict,
                verbose=False
            )
            
            elapsed = time.time() - start_time
            
            # Calculate precision
            relevant_count, precision = calculate_precision(docs, expected_keywords)
            
            # Extract metadata
            doc_ids = []
            similarity_scores = []
            for doc in docs:
                doc_id = doc.metadata.get("document_id", "N/A")
                # Truncate long IDs
                doc_ids.append(doc_id[:40] if len(doc_id) > 40 else doc_id)
                similarity_scores.append(doc.metadata.get("similarity_score", 0))
            
            result = RetrievalResult(
                no=no,
                query=query,
                retrieved_docs=len(docs),
                relevant_docs=relevant_count,
                precision=precision,
                time_seconds=elapsed,
                doc_ids=doc_ids,
                similarity_scores=similarity_scores
            )
            results.append(result)
            
            print(f"   ✅ Retrieved: {len(docs)}, Relevant: {relevant_count}, Precision: {precision:.2%}")
            print(f"   ⏱️  Time: {elapsed:.3f}s")
            if similarity_scores:
                print(f"   📊 Similarity: min={min(similarity_scores):.3f}, max={max(similarity_scores):.3f}, avg={sum(similarity_scores)/len(similarity_scores):.3f}")
        
        except Exception as e:
            results.append(RetrievalResult(
                no=no,
                query=query,
                retrieved_docs=0,
                relevant_docs=0,
                precision=0.0,
                time_seconds=0,
                error=str(e)
            ))
            print(f"   ❌ Error: {e}")
    
    return results


# ============================================================================
# RESPONSE QUALITY TESTING
# ============================================================================

def run_response_quality_tests(config_path: str) -> List[ResponseQualityResult]:
    """
    Jalankan pengujian Response Quality menggunakan QueryChain langsung
    """
    results = []
    
    print("\n" + "="*60)
    print("📝 PENGUJIAN RESPONSE QUALITY")
    print("="*60)
    
    # Get QueryChain singleton
    query_chain = get_query_chain(config_path)
    
    print(f"\n🤖 LLM Ready: {query_chain.llm is not None}")
    
    for query_config in RESPONSE_QUERIES:
        no = query_config["no"]
        query = query_config["query"]
        filter_dict = query_config.get("filter")
        
        print(f"\n[{no}/3] Testing: \"{query}\"")
        
        try:
            # Call QueryChain
            start_time = time.time()
            
            response = query_chain.query(
                question=query,
                filter=filter_dict,
                verbose=False
            )
            
            elapsed = time.time() - start_time
            
            answer = response.get("answer", "")
            sources = response.get("sources", [])
            metadata = response.get("metadata", {})
            
            # Auto-score
            relevance, accuracy, completeness = auto_score_response(
                query=query,
                answer=answer,
                sources=sources,
                metadata=metadata
            )
            
            average = (relevance + accuracy + completeness) / 3
            
            result = ResponseQualityResult(
                no=no,
                query=query,
                answer=answer,
                relevance=relevance,
                accuracy=accuracy,
                completeness=completeness,
                average=average,
                sources_count=len(sources),
                avg_similarity=metadata.get("avg_similarity", 0)
            )
            results.append(result)
            
            print(f"   ✅ Answer length: {len(answer)} chars")
            print(f"   📚 Sources: {len(sources)}")
            print(f"   📊 Scores: R={relevance}, A={accuracy}, C={completeness}, Avg={average:.2f}")
            print(f"   ⏱️  Time: {elapsed:.3f}s")
        
        except Exception as e:
            results.append(ResponseQualityResult(
                no=no,
                query=query,
                answer="",
                relevance=0,
                accuracy=0,
                completeness=0,
                average=0.0,
                sources_count=0,
                error=str(e)
            ))
            print(f"   ❌ Error: {e}")
    
    return results


# ============================================================================
# REPORT GENERATION
# ============================================================================

def generate_markdown_report(
    retrieval_results: List[RetrievalResult],
    response_results: List[ResponseQualityResult],
    output_path: str = "rag_performance_report.md"
) -> str:
    """
    Generate Markdown report sesuai format tabel yang diminta
    """
    report_lines = []
    
    # Header
    report_lines.append("# 4.2.1 Pengujian Performa RAG\n")
    report_lines.append("Pengujian performa RAG dilakukan untuk mengukur akurasi retrieval dan kualitas respons yang dihasilkan sistem.\n")
    report_lines.append(f"**Tanggal Pengujian:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # =========================================================================
    # RETRIEVAL ACCURACY
    # =========================================================================
    report_lines.append("\n## Pengujian Retrieval Accuracy\n")
    report_lines.append("Pengujian retrieval accuracy mengukur ketepatan sistem dalam mengambil dokumen yang relevan.\n")
    
    # Table header
    report_lines.append("**Tabel 4.13 Hasil Pengujian Retrieval Accuracy**\n")
    report_lines.append("| No | Query | Retrieved Docs | Relevant | Precision | Time (s) |")
    report_lines.append("|:--:|-------|:--------------:|:--------:|:---------:|:--------:|")
    
    # Table rows
    total_precision = 0
    total_time = 0
    valid_count = 0
    
    for r in retrieval_results:
        if r.error:
            report_lines.append(f"| {r.no} | {r.query} | Error | - | - | - |")
        else:
            precision_str = f"{r.precision:.2%}"
            time_str = f"{r.time_seconds:.3f}"
            report_lines.append(f"| {r.no} | {r.query} | {r.retrieved_docs} | {r.relevant_docs} | {precision_str} | {time_str} |")
            total_precision += r.precision
            total_time += r.time_seconds
            valid_count += 1
    
    # Summary
    if valid_count > 0:
        avg_precision = total_precision / valid_count
        avg_time = total_time / valid_count
        report_lines.append(f"\n**Rata-rata Precision:** {avg_precision:.2%}")
        report_lines.append(f"\n**Rata-rata Response Time:** {avg_time:.3f}s\n")
    
    # =========================================================================
    # RESPONSE QUALITY
    # =========================================================================
    report_lines.append("\n## Pengujian Response Quality\n")
    report_lines.append("Pengujian response quality mengukur kualitas jawaban yang dihasilkan oleh chatbot.\n")
    report_lines.append("Skala penilaian: 1 (Sangat Buruk) - 5 (Sangat Baik)\n")
    
    # Table header
    report_lines.append("**Tabel 4.14 Hasil Pengujian Response Quality**\n")
    report_lines.append("| No | Query | Relevance (1-5) | Accuracy (1-5) | Completeness (1-5) | Avg |")
    report_lines.append("|:--:|-------|:---------------:|:--------------:|:------------------:|:---:|")
    
    # Table rows
    total_avg = 0
    valid_count = 0
    
    for r in response_results:
        if r.error:
            report_lines.append(f"| {r.no} | {r.query} | Error | - | - | - |")
        else:
            avg_str = f"{r.average:.2f}"
            report_lines.append(f"| {r.no} | {r.query} | {r.relevance} | {r.accuracy} | {r.completeness} | {avg_str} |")
            total_avg += r.average
            valid_count += 1
    
    # Summary
    if valid_count > 0:
        overall_avg = total_avg / valid_count
        report_lines.append(f"\n**Rata-rata Keseluruhan:** {overall_avg:.2f}/5.00\n")
    
    # =========================================================================
    # DETAIL JAWABAN
    # =========================================================================
    report_lines.append("\n## Detail Jawaban Response Quality\n")
    for r in response_results:
        if not r.error:
            report_lines.append(f"\n### Query {r.no}: {r.query}\n")
            report_lines.append(f"**Jawaban:**\n")
            # Truncate jika terlalu panjang
            answer_display = r.answer if len(r.answer) <= 500 else r.answer[:500] + "..."
            report_lines.append(f"> {answer_display}\n")
            report_lines.append(f"\n**Jumlah Sumber:** {r.sources_count}")
            report_lines.append(f"\n**Rata-rata Similarity:** {r.avg_similarity:.3f}\n")
    
    # =========================================================================
    # KESIMPULAN
    # =========================================================================
    report_lines.append("\n## Kesimpulan Pengujian\n")
    
    # Retrieval summary
    valid_ret = [r for r in retrieval_results if not r.error]
    if valid_ret:
        avg_prec = sum(r.precision for r in valid_ret) / len(valid_ret)
        avg_time = sum(r.time_seconds for r in valid_ret) / len(valid_ret)
        report_lines.append(f"1. **Retrieval Accuracy:** Rata-rata precision mencapai {avg_prec:.2%} dengan waktu respons rata-rata {avg_time:.3f} detik.\n")
    
    # Response summary  
    valid_res = [r for r in response_results if not r.error]
    if valid_res:
        avg_score = sum(r.average for r in valid_res) / len(valid_res)
        report_lines.append(f"2. **Response Quality:** Rata-rata skor kualitas respons adalah {avg_score:.2f}/5.00.\n")
    
    # Write to file
    report_content = "\n".join(report_lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    
    print(f"\n✅ Report saved to: {output_path}")
    return report_content


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="RAG Performance Testing")
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=DEFAULT_CONFIG_PATH,
        help="Path to config.yaml"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="rag_performance_report.md",
        help="Output report path"
    )
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Only run retrieval accuracy tests"
    )
    parser.add_argument(
        "--response-only",
        action="store_true",
        help="Only run response quality tests"
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("🧪 RAG PERFORMANCE TESTING - DIRECT MODULE ACCESS")
    print("="*60)
    print(f"📁 Config: {args.config}")
    print(f"📄 Output: {args.output}")
    
    retrieval_results = []
    response_results = []
    
    try:
        # Run Retrieval Accuracy Tests
        if not args.response_only:
            retrieval_results = run_retrieval_accuracy_tests(args.config)
        
        # Run Response Quality Tests
        if not args.retrieval_only:
            response_results = run_response_quality_tests(args.config)
        
        # Generate Report
        print("\n" + "="*60)
        print("📄 GENERATING REPORT")
        print("="*60)
        
        generate_markdown_report(
            retrieval_results=retrieval_results,
            response_results=response_results,
            output_path=args.output
        )
        
        # Print Summary
        print("\n" + "="*60)
        print("📊 SUMMARY")
        print("="*60)
        
        if retrieval_results:
            valid_ret = [r for r in retrieval_results if not r.error]
            if valid_ret:
                avg_prec = sum(r.precision for r in valid_ret) / len(valid_ret)
                avg_time = sum(r.time_seconds for r in valid_ret) / len(valid_ret)
                print(f"\n📈 Retrieval Accuracy:")
                print(f"   - Tests: {len(valid_ret)}/{len(retrieval_results)} successful")
                print(f"   - Average Precision: {avg_prec:.2%}")
                print(f"   - Average Time: {avg_time:.3f}s")
        
        if response_results:
            valid_res = [r for r in response_results if not r.error]
            if valid_res:
                avg_score = sum(r.average for r in valid_res) / len(valid_res)
                print(f"\n📝 Response Quality:")
                print(f"   - Tests: {len(valid_res)}/{len(response_results)} successful")
                print(f"   - Average Score: {avg_score:.2f}/5.00")
        
        print("\n✅ Testing completed!")
        
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()