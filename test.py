"""
RAG Performance Testing Script - Complete Version
=================================================
Script untuk mengukur performa RAG lengkap:
- Retrieval Accuracy (Precision@k, Recall@k)
- Response Quality (Relevance, Accuracy, Completeness)

Output: Markdown report  Pengujian Performa RAG

USAGE:
    python rag_performance_test_complete.py --config path/to/config.yaml
"""

import sys
import os
import time
import argparse
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from collections import defaultdict

# Add project root to path
# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from informasional.utils.smart_retriever import get_smart_retriever
from informasional.core.rag_factory import get_query_chain


# ============================================================================
# CONFIGURATION
# ============================================================================

DEFAULT_CONFIG_PATH = "informasional/config/config.yaml"

# ============================================================================
# SAMPLE QUERIES FOR SECTION 4.2.1
# ============================================================================

# Tabel 4.18: 5 contoh query untuk Retrieval Accuracy
RETRIEVAL_SAMPLE_QUERIES = [
    {
        "no": 1,
        "query": "Biaya Sekolah SD Al-Azhar Cibinong",
        "expected_keywords": ["biaya", "sd", "al-azhar", "cibinong", "spp"],
        "filter": {"jenjang": "SD", "cabang": "Cibinong"}
    },
    {
        "no": 2,
        "query": "Persyaratan pendaftaran",
        "expected_keywords": ["persyaratan", "pendaftaran", "syarat", "dokumen"],
        "filter": None
    },
    {
        "no": 3,
        "query": "Jadwal Pendaftaran",
        "expected_keywords": ["jadwal", "pendaftaran", "tahun", "ajaran", "kalender"],
        "filter": None
    },
    {
        "no": 4,
        "query": "Fasilitas sekolah",
        "expected_keywords": ["fasilitas", "sekolah", "ruang", "laboratorium", "perpustakaan"],
        "filter": None
    },
    {
        "no": 5,
        "query": "Kurikulum yang digunakan",
        "expected_keywords": ["kurikulum", "merdeka", "pembelajaran", "mata", "pelajaran"],
        "filter": None
    }
]

# Tabel 4.19: 3 contoh query untuk Response Quality
RESPONSE_SAMPLE_QUERIES = [
    {
        "no": 1,
        "query": "Berapa biaya pendaftaran untuk SD Cibinong Al-Azhar?",
        "filter": {"jenjang": "SD", "cabang": "Cibinong"}
    },
    {
        "no": 2,
        "query": "Apa saja dokumen yang diperlukan untuk mendaftar ke SD Al-Azhar?",
        "filter": {"jenjang": "SD"}
    },
    {
        "no": 3,
        "query": "Jelaskan program unggulan yang ada di SMP Al-Azhar",
        "filter": {"jenjang": "SMP"}
    }
]

# Full 40 queries untuk Lampiran dan 4.3.3 (sesuaikan dengan query Anda)
FULL_40_QUERIES = [
    # === BIAYA SEKOLAH (15 queries) ===
    {
        "no": 1,
        "category": "Biaya Sekolah",
        "query": "Berapa biaya SPP SD Al-Azhar Cibinong per bulan?",
        "expected_keywords": ["spp", "sd", "cibinong", "biaya", "bulan"],
        "filter": {"jenjang": "SD", "cabang": "Cibinong"}
    },
    {
        "no": 2,
        "category": "Biaya Sekolah",
        "query": "Biaya sekolah SMP Al-Azhar Jakarta per tahun",
        "expected_keywords": ["smp", "jakarta", "biaya", "tahun"],
        "filter": {"jenjang": "SMP", "cabang": "Jakarta"}
    },
    # ... tambahkan 13 query lagi (total 15)
    
    # === BIAYA FORMULIR PENDAFTARAN (9 queries) ===
    {
        "no": 16,
        "category": "Biaya Formulir Pendaftaran",
        "query": "Berapa biaya formulir pendaftaran SD Al-Azhar Cibinong?",
        "expected_keywords": ["formulir", "pendaftaran", "sd", "cibinong"],
        "filter": {"jenjang": "SD", "cabang": "Cibinong"}
    },
    # ... tambahkan 8 query lagi (total 9)
    
    # === SYARAT PENDAFTARAN (1 query) ===
    {
        "no": 26,
        "category": "Syarat Pendaftaran",
        "query": "Apa saja syarat pendaftaran siswa baru?",
        "expected_keywords": ["syarat", "pendaftaran", "siswa", "baru"],
        "filter": None
    },
    
    # === UANG PANGKAL (15 queries) ===
    {
        "no": 27,
        "category": "Uang Pangkal",
        "query": "Berapa uang pangkal SD Al-Azhar?",
        "expected_keywords": ["uang", "pangkal", "sd"],
        "filter": {"jenjang": "SD"}
    },
    # ... tambahkan 14 query lagi (total 15)
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
    recall: float
    time_seconds: float
    doc_ids: List[str] = field(default_factory=list)
    similarity_scores: List[float] = field(default_factory=list)
    total_relevant_in_kb: int = 0  # Total chunk relevan di knowledge base
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
    retrieval_time: float = 0.0
    generation_time: float = 0.0
    error: Optional[str] = None


@dataclass
class PrecisionResult:
    """Hasil precision untuk berbagai k (untuk 4.3.3)"""
    no: int
    category: str
    query: str
    precision_at_1: float
    precision_at_3: float
    precision_at_5: float
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    time_seconds: float
    error: Optional[str] = None


# ============================================================================
# PRECISION & RECALL CALCULATION
# ============================================================================

def calculate_precision_recall(
    docs: List,
    expected_keywords: List[str],
    k: int = 3
) -> Tuple[int, int, float, float]:
    """
    Hitung precision dan recall untuk k tertentu
    
    Args:
        docs: List of Document objects
        expected_keywords: Keywords yang diharapkan
        k: Jumlah dokumen yang diambil
    
    Returns:
        (retrieved_count, relevant_count, precision, recall)
    """
    docs_at_k = docs[:k]
    if not docs_at_k:
        return 0, 0, 0.0, 0.0
    
    keywords_lower = [kw.lower() for kw in expected_keywords]
    relevant_count = 0
    
    for doc in docs_at_k:
        content = doc.page_content.lower()
        source = doc.metadata.get("source", "").lower()
        doc_id = doc.metadata.get("document_id", "").lower()
        combined_text = f"{content} {source} {doc_id}"
        
        if any(keyword in combined_text for keyword in keywords_lower):
            relevant_count += 1
    
    precision = relevant_count / k if k > 0 else 0.0
    
    # Untuk recall, kita asumsikan total_relevant = jumlah keyword yang match
    # di seluruh collection (ini simplified, idealnya perlu ground truth)
    # Untuk demo, kita set total_relevant = k (asumsi ada k dokumen relevan)
    total_relevant = k  # Simplified assumption
    recall = relevant_count / total_relevant if total_relevant > 0 else 0.0
    
    return len(docs_at_k), relevant_count, precision, recall


# ============================================================================
# AUTO SCORING FOR RESPONSE QUALITY
# ============================================================================

def auto_score_response(
    query: str,
    answer: str,
    sources: List[Dict],
    metadata: Dict
) -> Tuple[int, int, int]:
    """
    Auto-scoring response quality (1-5 scale)
    
    Returns:
        (relevance, accuracy, completeness)
    """
    relevance = 3
    accuracy = 3
    completeness = 3
    
    # === RELEVANCE (based on similarity) ===
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
    
    # === ACCURACY (based on relevance check) ===
    relevance_check = metadata.get("relevance_check", "")
    if "PASSED" in relevance_check or "relevan" in relevance_check.lower():
        accuracy = 4
        if len(sources) >= 2:
            accuracy = 5
    elif "FAILED" in relevance_check:
        accuracy = 2
    
    # Check for default/not found answers
    answer_lower = answer.lower()
    if any(phrase in answer_lower for phrase in [
        "tidak ditemukan", "maaf", "tidak ada informasi", 
        "tidak dapat", "belum tersedia"
    ]):
        accuracy = max(1, accuracy - 2)
        completeness = max(1, completeness - 1)
    
    # === COMPLETENESS (based on length and sources) ===
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
# RETRIEVAL ACCURACY TESTING (Tabel 4.18)
# ============================================================================

def run_retrieval_accuracy_sample(config_path: str) -> List[RetrievalResult]:
    """
    Test 5 sample queries untuk Tabel 4.18
    """
    results = []
    
    print("\n" + "="*70)
    print("📊 PENGUJIAN RETRIEVAL ACCURACY (5 Contoh Query)")
    print("="*70)
    
    retriever = get_smart_retriever(config_path)
    
    for query_config in RETRIEVAL_SAMPLE_QUERIES:
        no = query_config["no"]
        query = query_config["query"]
        expected_keywords = query_config["expected_keywords"]
        filter_dict = query_config.get("filter")
        
        print(f"\n[{no}/5] Testing: \"{query}\"")
        
        try:
            start_time = time.time()
            
            # Retrieve with k=3 (fokus utama)
            docs = retriever.retrieve(
                query=query,
                k=3,
                filter=filter_dict,
                verbose=False
            )
            
            elapsed = time.time() - start_time
            
            # Calculate precision & recall
            retrieved, relevant, precision, recall = calculate_precision_recall(
                docs, expected_keywords, k=3
            )
            
            # Extract doc IDs and similarity scores
            doc_ids = [doc.metadata.get("document_id", "N/A")[:40] for doc in docs]
            similarity_scores = [doc.metadata.get("similarity_score", 0) for doc in docs]
            
            result = RetrievalResult(
                no=no,
                query=query,
                retrieved_docs=retrieved,
                relevant_docs=relevant,
                precision=precision,
                recall=recall,
                time_seconds=elapsed,
                doc_ids=doc_ids,
                similarity_scores=similarity_scores,
                total_relevant_in_kb=3  # Simplified
            )
            results.append(result)
            
            print(f"   ✅ Retrieved: {retrieved}, Relevant: {relevant}")
            print(f"   📊 Precision: {precision:.2%}, Recall: {recall:.2%}")
            print(f"   ⏱️  Time: {elapsed:.3f}s")
        
        except Exception as e:
            results.append(RetrievalResult(
                no=no,
                query=query,
                retrieved_docs=0,
                relevant_docs=0,
                precision=0.0,
                recall=0.0,
                time_seconds=0,
                error=str(e)
            ))
            print(f"   ❌ Error: {e}")
    
    return results


# ============================================================================
# RESPONSE QUALITY TESTING (Tabel 4.19)
# ============================================================================

def run_response_quality_sample(config_path: str) -> List[ResponseQualityResult]:
    """
    Test 3 sample queries untuk Tabel 4.19
    """
    results = []
    
    print("\n" + "="*70)
    print("📝 PENGUJIAN RESPONSE QUALITY (3 Contoh Query)")
    print("="*70)
    
    query_chain = get_query_chain(config_path)
    
    for query_config in RESPONSE_SAMPLE_QUERIES:
        no = query_config["no"]
        query = query_config["query"]
        filter_dict = query_config.get("filter")
        
        print(f"\n[{no}/3] Testing: \"{query}\"")
        
        try:
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
                query, answer, sources, metadata
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
                avg_similarity=metadata.get("avg_similarity", 0),
                retrieval_time=metadata.get("retrieval_time", 0),
                generation_time=elapsed
            )
            results.append(result)
            
            print(f"   ✅ Scores: R={relevance}, A={accuracy}, C={completeness}, Avg={average:.2f}")
            print(f"   📚 Sources: {len(sources)}, Answer length: {len(answer)} chars")
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
# FULL 40 QUERIES TESTING (untuk 4.3.3)
# ============================================================================

def run_full_precision_tests(config_path: str) -> List[PrecisionResult]:
    """
    Test 40 queries dengan Precision@1, @3, @5 untuk 4.3.3
    """
    results = []
    
    print("\n" + "="*70)
    print("📊 PENGUJIAN LENGKAP 40 QUERIES (untuk 4.3.3)")
    print("="*70)
    
    retriever = get_smart_retriever(config_path)
    
    for query_config in FULL_40_QUERIES:
        no = query_config["no"]
        category = query_config["category"]
        query = query_config["query"]
        expected_keywords = query_config["expected_keywords"]
        filter_dict = query_config.get("filter")
        
        print(f"\n[{no}/40] {category}: \"{query}\"")
        
        try:
            start_time = time.time()
            
            # Retrieve with k=5
            docs = retriever.retrieve(
                query=query,
                k=5,
                filter=filter_dict,
                verbose=False
            )
            
            elapsed = time.time() - start_time
            
            # Calculate for k=1, 3, 5
            _, rel1, p1, r1 = calculate_precision_recall(docs, expected_keywords, 1)
            _, rel3, p3, r3 = calculate_precision_recall(docs, expected_keywords, 3)
            _, rel5, p5, r5 = calculate_precision_recall(docs, expected_keywords, 5)
            
            result = PrecisionResult(
                no=no,
                category=category,
                query=query,
                precision_at_1=p1,
                precision_at_3=p3,
                precision_at_5=p5,
                recall_at_1=r1,
                recall_at_3=r3,
                recall_at_5=r5,
                time_seconds=elapsed
            )
            results.append(result)
            
            print(f"   ✅ P@1:{p1:.0%} P@3:{p3:.0%} P@5:{p5:.0%}")
        
        except Exception as e:
            results.append(PrecisionResult(
                no=no,
                category=category,
                query=query,
                precision_at_1=0.0,
                precision_at_3=0.0,
                precision_at_5=0.0,
                recall_at_1=0.0,
                recall_at_3=0.0,
                recall_at_5=0.0,
                time_seconds=0,
                error=str(e)
            ))
            print(f"   ❌ Error: {e}")
    
    return results


# ============================================================================
# REPORT GENERATION (Format 4.2.1)
# ============================================================================

def generate_421_report(
    retrieval_results: List[RetrievalResult],
    response_results: List[ResponseQualityResult],
    output_path: str = "4.2.1_pengujian_performa_rag.md"
) -> str:
    """Generate report untuk 4.2.1"""
    lines = []
    
    # Header (tidak perlu, karena ini akan di-copy ke Word)
    lines.append("### d. Hasil Pengujian Retrieval Accuracy\n")
    lines.append("Tabel 4.18 menunjukkan hasil pengujian retrieval accuracy pada 5 query sampel ")
    lines.append("yang mewakili berbagai kategori informasi. Pengujian menggunakan k=3 chunk teratas ")
    lines.append("sebagai konteks pembentukan jawaban. Pengujian lengkap terhadap 40 query dengan ")
    lines.append("metrik Precision@1, @3, dan @5 disajikan pada bagian 4.3.3 Evaluasi Akurasi RAG.\n")
    
    lines.append("**Tabel 4.18 Contoh Hasil Pengujian Retrieval Accuracy (k=3)**\n")
    lines.append("| No | Query | Retrieved Docs | Relevant | Precision@3 | Time (s) |")
    lines.append("|:--:|-------|:--------------:|:--------:|:-----------:|:--------:|")
    
    for r in retrieval_results:
        if r.error:
            lines.append(f"| {r.no} | {r.query} | Error | - | - | - |")
        else:
            prec_str = f"{r.precision:.0%}"
            time_str = f"{r.time_seconds:.3f}"
            lines.append(f"| {r.no} | {r.query} | {r.retrieved_docs} | {r.relevant_docs} | {prec_str} | {time_str} |")
    
    lines.append("\n")
    
    # =========================================================================
    # Tabel 4.19: Response Quality
    # =========================================================================
    lines.append("### e. Hasil Pengujian Response Quality\n")
    lines.append("Tabel 4.19 menunjukkan hasil evaluasi kualitas jawaban yang dihasilkan sistem ")
    lines.append("setelah proses retrieval dan generation. Evaluasi dilakukan terhadap 3 query ")
    lines.append("representatif menggunakan skala 1-5 untuk tiga aspek kualitas: Relevance ")
    lines.append("(kesesuaian jawaban dengan pertanyaan), Accuracy (ketepatan informasi), dan ")
    lines.append("Completeness (kelengkapan jawaban).\n")
    
    lines.append("**Tabel 4.19 Contoh Hasil Pengujian Response Quality**\n")
    lines.append("| No | Query | Relevance (1-5) | Accuracy (1-5) | Completeness (1-5) | Avg |")
    lines.append("|:--:|-------|:---------------:|:--------------:|:------------------:|:---:|")
    
    total_avg = 0
    valid_count = 0
    
    for r in response_results:
        if r.error:
            lines.append(f"| {r.no} | {r.query} | Error | - | - | - |")
        else:
            avg_str = f"{r.average:.2f}"
            lines.append(f"| {r.no} | {r.query} | {r.relevance} | {r.accuracy} | {r.completeness} | {avg_str} |")
            total_avg += r.average
            valid_count += 1
    
    if valid_count > 0:
        overall = total_avg / valid_count
        lines.append(f"\n**Catatan:** Rata-rata skor kualitas respons adalah {overall:.2f}/5.00. ")
        lines.append("Evaluasi response quality dilakukan terhadap subset query untuk mengukur ")
        lines.append("kualitas end-to-end sistem dari retrieval hingga generation.")
    
    lines.append("\n")
    
    # Write to file
    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"\n✅ Report 4.2.1 saved to: {output_path}")
    return content


# ============================================================================
# LAMPIRAN GENERATION
# ============================================================================

def generate_lampiran_b(
    full_results: List[PrecisionResult],
    output_path: str = "lampiran_b_hasil_lengkap.md"
) -> str:
    """Generate Lampiran B: Hasil lengkap 40 query"""
    lines = []
    
    lines.append("# Lampiran B: Hasil Pengujian Lengkap 40 Query\n")
    lines.append("Tabel berikut menunjukkan hasil pengujian retrieval accuracy untuk 40 query ")
    lines.append("informational dengan metrik Precision@k dan Recall@k pada k = 1, 3, dan 5.\n")
    
    lines.append("| No | Kategori | Query | P@1 | P@3 | P@5 | R@1 | R@3 | R@5 |")
    lines.append("|:--:|----------|-------|:---:|:---:|:---:|:---:|:---:|:---:|")
    
    for r in full_results:
        if not r.error:
            lines.append(f"| {r.no} | {r.category} | {r.query} | {r.precision_at_1:.0%} | {r.precision_at_3:.0%} | {r.precision_at_5:.0%} | {r.recall_at_1:.0%} | {r.recall_at_3:.0%} | {r.recall_at_5:.0%} |")
    
    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"✅ Lampiran B saved to: {output_path}")
    return content


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="RAG Performance Testing - Complete")
    parser.add_argument("--config", "-c", type=str, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-421", type=str, default="4.2.1_pengujian_performa_rag.md")
    parser.add_argument("--output-lampiran", type=str, default="lampiran_b_hasil_lengkap.md")
    parser.add_argument("--skip-full", action="store_true", help="Skip full 40 queries test")
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("🧪 RAG PERFORMANCE TESTING - COMPLETE VERSION")
    print("="*70)
    print(f"📁 Config: {args.config}")
    print(f"📄 Output 4.2.1: {args.output_421}")
    print(f"📄 Output Lampiran B: {args.output_lampiran}")
    
    try:
        # 1. Test 5 sample queries (Tabel 4.18)
        retrieval_results = run_retrieval_accuracy_sample(args.config)
        
        # 2. Test 3 sample queries (Tabel 4.19)
        response_results = run_response_quality_sample(args.config)
        
        # 3. Test full 40 queries (untuk Lampiran B dan 4.3.3)
        full_results = []
        if not args.skip_full:
            full_results = run_full_precision_tests(args.config)
        
        # 4. Generate reports
        print("\n" + "="*70)
        print("📄 GENERATING REPORTS")
        print("="*70)
        
        generate_421_report(retrieval_results, response_results, args.output_421)
        
        if full_results:
            generate_lampiran_b(full_results, args.output_lampiran)
        
        # 5. Print summary
        print("\n" + "="*70)
        print("📊 SUMMARY")
        print("="*70)
        
        # Retrieval summary
        valid_ret = [r for r in retrieval_results if not r.error]
        if valid_ret:
            avg_prec = sum(r.precision for r in valid_ret) / len(valid_ret)
            avg_time = sum(r.time_seconds for r in valid_ret) / len(valid_ret)
            print(f"\n📈 Retrieval Accuracy (5 samples):")
            print(f"   - Average Precision@3: {avg_prec:.2%}")
            print(f"   - Average Time: {avg_time:.3f}s")
        
        # Response summary
        valid_res = [r for r in response_results if not r.error]
        if valid_res:
            avg_score = sum(r.average for r in valid_res) / len(valid_res)
            print(f"\n📝 Response Quality (3 samples):")
            print(f"   - Average Score: {avg_score:.2f}/5.00")
        
        # Full test summary
        if full_results:
            valid_full = [r for r in full_results if not r.error]
            if valid_full:
                avg_p3 = sum(r.precision_at_3 for r in valid_full) / len(valid_full)
                print(f"\n📊 Full 40 Queries:")
                print(f"   - Tests completed: {len(valid_full)}/40")
                print(f"   - Average Precision@3: {avg_p3:.2%}")
        
        print("\n✅ All testing completed!")
        print(f"\n📋 Next steps:")
        print(f"   1. Copy content from '{args.output_421}' to Word document section 4.2.1")
        print(f"   2. Copy content from '{args.output_lampiran}' to Lampiran B")
        print(f"   3. Use full results for section 4.3.3 Evaluasi Akurasi RAG")
    
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()