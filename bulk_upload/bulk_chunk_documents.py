import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import time
from sqlalchemy.orm import Session
from informasional.utils.enhanced_chunker import EnhancedChunker, DocumentProcessor
from informasional.utils.metadata_extractor import MetadataExtractor
from informasional.utils.db import SessionLocal
from informasional.repositories.master_repository import MasterRepository
from informasional.repositories.document_repository import DocumentRepository

# ==============================
# CONFIG
# ==============================
CONFIG_PATH = "informasional/config/config.yaml"
SLEEP_BETWEEN_DOCS = 0.5  # detik, hindari overload DB

# ==============================
# ENTRY POINT
# ==============================
def main():
    db: Session = SessionLocal()
    try:
        # Inisialisasi
        chunker = EnhancedChunker(config_path=CONFIG_PATH)
        master_repo = MasterRepository(db)
        docrepo = DocumentRepository(db)
        extractor = MetadataExtractor(master_repo)
        processor = DocumentProcessor(chunker=chunker, metadata_extractor=extractor)

        # Ambil semua dokumen yang sudah diproses
        documents, total = docrepo.get_all(status="completed", limit=1000)
        print(f"📄 Found {total} documents")

        total_chunks_saved = 0

        for idx, db_doc in enumerate(documents, start=1):
            print(f"\n⚙️ Processing document [{idx}/{total}] ID={db_doc.id} | {db_doc.filename}")

            # Skip dokumen kosong
            if not db_doc.raw_text or not db_doc.raw_text.strip():
                print(f"❌ Document ID={db_doc.id} has no extracted text, skipping...")
                continue

            doc_data = {
                "filename": db_doc.original_filename or db_doc.filename,
                "content": db_doc.raw_text,
                "document_id": db_doc.id,
                "metadata": db_doc.extra_metadata or {}  # <-- pastikan dict
            }

            try:
                # Chunking
                chunks = processor.process_multiple_documents([doc_data])
                saved_chunks = []

                for chunk in chunks:
                    if chunk is None:
                        continue
                    metadata = chunk.metadata or {}
                    filename = metadata.get("filename")
                    saved = master_repo.save_chunk(
                        content=chunk.page_content,
                        metadata=metadata,
                        filename=filename
                    )
                    saved_chunks.append(saved)

                total_chunks_saved += len(saved_chunks)
                print(f"✅ Saved {len(saved_chunks)} chunks for document ID={db_doc.id}")

            except Exception as e:
                print(f"❌ Failed to chunk document ID={db_doc.id} | Error: {str(e)}")

            time.sleep(SLEEP_BETWEEN_DOCS)

        print("\n==============================")
        print("📊 BULK CHUNKING SUMMARY")
        print("==============================")
        print(f"Total documents processed : {total}")
        print(f"Total chunks saved        : {total_chunks_saved}")
        print("==============================")

    finally:
        db.close()


if __name__ == "__main__":
    main()
