#!/usr/bin/env python3
# ============================================================================
# FILE: test_rag_solution.py
# ============================================================================
"""
Test Script untuk validasi RAG Solution

Jalankan: python test_rag_solution.py

Test cases:
1. Chunking dengan document_id konsisten
2. Metadata lengkap
3. Document aggregation
4. Context building
"""

import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.enhanced_chunker import EnhancedChunker
from utils.smart_retriever import SmartRetriever


def print_header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_success(msg: str):
    print(f"  ✅ {msg}")


def print_fail(msg: str):
    print(f"  ❌ {msg}")


def print_info(msg: str):
    print(f"  ℹ️  {msg}")


# ============================================================================
# TEST 1: CHUNKING
# ============================================================================
def test_chunking():
    print_header("TEST 1: CHUNKING dengan Document ID Konsisten")
    
    config = {
        "chunking": {
            "fixed_size": {
                "chunk_size": 300,
                "chunk_overlap": 50,
                "separators": ["\n\n", "\n", ".", " ", ""]
            }
        }
    }
    
    chunker = EnhancedChunker(config=config)
    
    # Sample content panjang
    content = """
    YPI Al-Azhar Jakarta adalah yayasan pendidikan Islam terkemuka di Indonesia.
    Didirikan pada tahun 1952, yayasan ini telah berkembang menjadi salah satu 
    lembaga pendidikan terbesar di Indonesia.
    
    Biaya Pendidikan Tahun Ajaran 2024/2025:
    
    Jenjang SD:
    - Uang Pangkal: Rp 25.000.000
    - SPP Bulanan: Rp 1.500.000
    - Uang Kegiatan: Rp 500.000/semester
    
    Jenjang SMP:
    - Uang Pangkal: Rp 30.000.000
    - SPP Bulanan: Rp 1.800.000
    - Uang Kegiatan: Rp 600.000/semester
    
    Jenjang SMA:
    - Uang Pangkal: Rp 35.000.000
    - SPP Bulanan: Rp 2.000.000
    - Uang Kegiatan: Rp 750.000/semester
    
    Program Unggulan:
    1. Tahfidz Al-Quran - Program menghafal Al-Quran dengan target 5 juz
    2. Bilingual Program - Pembelajaran dalam Bahasa Indonesia dan Inggris
    3. Science Club - Klub sains untuk pengembangan minat STEM
    4. Leadership Camp - Program pengembangan kepemimpinan siswa
    
    Fasilitas:
    - Perpustakaan modern dengan koleksi 50.000 buku
    - Laboratorium IPA, Komputer, dan Bahasa
    - Lapangan olahraga (basket, futsal, badminton)
    - Masjid dengan kapasitas 1000 jamaah
    - Kantin sehat dengan sertifikasi halal
    
    Untuk informasi lebih lanjut, hubungi:
    - Telepon: (021) 1234567
    - WhatsApp: 0812-3456-7890
    - Email: info@alazhar.sch.id
    - Website: www.alazhar.sch.id
    """
    
    metadata = {
        "source": "brosur_biaya_2024.pdf",
        "jenjang": "SD, SMP, SMA",
        "tahun": "2024/2025",
        "cabang": "Pusat Jakarta"
    }
    
    # Chunk
    chunks = chunker.chunk_document(content, metadata)
    
    print(f"\n  📄 Original content: {len(content)} chars")
    print(f"  ✂️  Chunked into: {len(chunks)} chunks")
    
    # Test 1.1: Document ID konsisten
    doc_ids = set(c.metadata['document_id'] for c in chunks)
    if len(doc_ids) == 1:
        print_success(f"Document ID konsisten: {list(doc_ids)[0]}")
    else:
        print_fail(f"Document ID TIDAK konsisten! Found: {doc_ids}")
        return False
    
    # Test 1.2: Chunk index berurutan
    indices = [c.metadata['chunk_index'] for c in chunks]
    expected = list(range(len(chunks)))
    if indices == expected:
        print_success(f"Chunk indices berurutan: {indices}")
    else:
        print_fail(f"Chunk indices TIDAK urut! Found: {indices}")
        return False
    
    # Test 1.3: Total chunks metadata
    total_chunks_meta = [c.metadata['total_chunks'] for c in chunks]
    if all(t == len(chunks) for t in total_chunks_meta):
        print_success(f"Total chunks metadata benar: {len(chunks)}")
    else:
        print_fail(f"Total chunks metadata SALAH! Found: {total_chunks_meta}")
        return False
    
    # Test 1.4: First/Last chunk flags
    if chunks[0].metadata['is_first_chunk'] and not chunks[0].metadata['is_last_chunk']:
        print_success("First chunk flag benar")
    else:
        print_fail("First chunk flag SALAH!")
        return False
    
    if chunks[-1].metadata['is_last_chunk'] and not chunks[-1].metadata['is_first_chunk']:
        print_success("Last chunk flag benar")
    else:
        print_fail("Last chunk flag SALAH!")
        return False
    
    # Test 1.5: Navigation links
    has_nav = all(
        (c.metadata.get('prev_chunk_id') is not None or c.metadata['is_first_chunk']) and
        (c.metadata.get('next_chunk_id') is not None or c.metadata['is_last_chunk'])
        for c in chunks
    )
    if has_nav:
        print_success("Navigation links (prev/next) tersedia")
    else:
        print_fail("Navigation links TIDAK lengkap!")
        return False
    
    # Print sample chunk
    print(f"\n  📋 Sample Chunk Metadata:")
    sample = chunks[1].metadata if len(chunks) > 1 else chunks[0].metadata
    for key in ['document_id', 'chunk_id', 'chunk_index', 'total_chunks', 
                'is_first_chunk', 'is_last_chunk', 'source', 'jenjang', 'tahun']:
        print(f"     {key}: {sample.get(key)}")
    
    return True


# ============================================================================
# TEST 2: STATISTICS
# ============================================================================
def test_statistics():
    print_header("TEST 2: CHUNKING STATISTICS")
    
    config = {
        "chunking": {
            "fixed_size": {
                "chunk_size": 500,
                "chunk_overlap": 100,
                "separators": ["\n\n", "\n", ".", " ", ""]
            }
        }
    }
    
    chunker = EnhancedChunker(config=config)
    
    # Multiple documents
    documents = [
        {
            "content": "Dokumen 1 tentang biaya SPP. " * 50,
            "metadata": {"source": "doc1.pdf", "jenjang": "SD"}
        },
        {
            "content": "Dokumen 2 tentang pendaftaran. " * 40,
            "metadata": {"source": "doc2.pdf", "jenjang": "SMP"}
        },
        {
            "content": "Dokumen 3 tentang kurikulum. " * 30,
            "metadata": {"source": "doc3.pdf", "jenjang": "SMA"}
        }
    ]
    
    all_chunks = chunker.chunk_multiple_documents(documents)
    stats = chunker.get_statistics(all_chunks)
    
    print(f"\n  📊 Statistics:")
    print(f"     Total chunks: {stats['total_chunks']}")
    print(f"     Total documents: {stats['total_documents']}")
    print(f"     Avg chunk length: {stats['avg_chunk_length']} chars")
    print(f"     Min chunk length: {stats['min_chunk_length']} chars")
    print(f"     Max chunk length: {stats['max_chunk_length']} chars")
    
    # Validate
    if stats['total_documents'] == 3:
        print_success("Document count benar")
    else:
        print_fail(f"Document count SALAH! Expected 3, got {stats['total_documents']}")
        return False
    
    if stats['total_chunks'] > 0:
        print_success(f"Total chunks: {stats['total_chunks']}")
    else:
        print_fail("No chunks created!")
        return False
    
    return True


# ============================================================================
# TEST 3: METADATA SANITIZATION
# ============================================================================
def test_metadata_sanitization():
    print_header("TEST 3: METADATA untuk ChromaDB")
    
    chunker = EnhancedChunker(config={
        "chunking": {"fixed_size": {"chunk_size": 500, "chunk_overlap": 100}}
    })
    
    # Metadata dengan berbagai tipe
    content = "Test content untuk metadata validation. " * 20
    metadata = {
        "source": "test.pdf",
        "jenjang": "SD",
        "tahun": 2024,  # int
        "is_active": True,  # bool
        "score": 0.95,  # float
        "tags": ["biaya", "SPP", "pendidikan"],  # list
        "extra": None  # None
    }
    
    chunks = chunker.chunk_document(content, metadata)
    
    # Cek metadata di chunk
    meta = chunks[0].metadata
    
    print(f"\n  📋 Metadata types:")
    
    # Check required fields exist
    required = ['document_id', 'chunk_id', 'chunk_index', 'source']
    all_present = all(field in meta for field in required)
    
    if all_present:
        print_success("Required fields present")
    else:
        missing = [f for f in required if f not in meta]
        print_fail(f"Missing fields: {missing}")
        return False
    
    # Check types are ChromaDB compatible (str, int, float, bool)
    for key, value in meta.items():
        vtype = type(value).__name__
        if value is None or isinstance(value, (str, int, float, bool)):
            print(f"     {key}: {vtype} ✓")
        else:
            print(f"     {key}: {vtype} ✗ (not ChromaDB compatible)")
            return False
    
    print_success("All metadata types ChromaDB compatible")
    return True


# ============================================================================
# MAIN
# ============================================================================
def main():
    print("\n" + "="*60)
    print("  RAG SOLUTION TEST SUITE")
    print("="*60)
    
    results = []
    
    # Run tests
    results.append(("Chunking", test_chunking()))
    results.append(("Statistics", test_statistics()))
    results.append(("Metadata", test_metadata_sanitization()))
    
    # Summary
    print_header("TEST SUMMARY")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {name}: {status}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n  🎉 ALL TESTS PASSED!")
        return 0
    else:
        print("\n  ⚠️  SOME TESTS FAILED!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
