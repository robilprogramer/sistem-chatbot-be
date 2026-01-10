import requests
from sqlalchemy.orm import Session
from datetime import datetime
from informasional.repositories.document_repository import DocumentRepository
from informasional.models.document import DocumentStatus


class BulkChunkingService:
    def __init__(self, db: Session, base_url: str):
        """
        :param db: SQLAlchemy session
        :param base_url: contoh http://localhost:8000/
        """
        self.db = db
        self.base_url = base_url
        self.document_repo = DocumentRepository(db)

    def process_all_documents(self, page_size: int = 50):
        """
        Ambil semua dokumen, lalu kirim satu per satu ke API /process
        """
        skip = 0

        while True:
            documents, total = self.document_repo.get_all(
                skip=skip,
                limit=page_size
            )

            if not documents:
                print("✅ Semua dokumen sudah diproses")
                break

            print(f"📄 Memproses {len(documents)} dokumen (offset {skip})")

            for document in documents:
                self._process_single_document(document)

            skip += page_size

    def _process_single_document(self, document):
        if not document.raw_text:
            print(f"⚠️ Skip document ID {document.id} (raw_text kosong)")
            return

        payload = {
            "documents": [
                {
                    "filename": document.original_filename,
                    "content": document.raw_text
                }
            ]
        }

        try:
            print(f"🚀 Processing document ID {document.id}")

            response = requests.post(
                f"{self.base_url}/process",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=300
            )

            if not response.ok:
                raise Exception(response.text)

            print(f"✅ Success document ID {document.id}")
            return response.json()

        except Exception as e:
            print(f"❌ Failed document ID {document.id}: {str(e)}")
            return None


