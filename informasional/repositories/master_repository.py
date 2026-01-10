from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import text
from informasional.models.chunk import ChunkModel
class MasterRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_jenjang(self) -> List[str]:
        result = self.db.execute(
            text("SELECT kode FROM master_jenjang")
        )
        return [row[0] for row in result.fetchall()]

    def get_cabang(self) -> List[str]:
        result = self.db.execute(
            text("SELECT nama FROM master_cabang")
        )
        return [row[0].lower() for row in result.fetchall()]

    def get_kategori(self) -> List[str]:
        result = self.db.execute(
            text("SELECT nama FROM master_kategori")
        )
        return [row[0].lower() for row in result.fetchall()]
    
    def save_chunk(self, content: str, metadata: dict, filename: str = None):
        chunk = ChunkModel(
            content=content,
            metadata_json=metadata,
            filename=filename
        )
        self.db.add(chunk)
        self.db.commit()
        self.db.refresh(chunk)  # biar chunk.id terisi
        return chunk

    # READ
    def get_chunk(self, chunk_id: int):
        return self.db.query(ChunkModel).filter(ChunkModel.id == chunk_id).first()

    def get_all_chunks(self, skip: int = 0, limit: int = 100):
        return self.db.query(ChunkModel).offset(skip).limit(limit).all()

    # UPDATE
    def update_chunk(self, chunk_id: int, content: str = None, metadata: dict = None, filename: str = None):
        chunk = self.get_chunk(chunk_id)
        if not chunk:
            return None

        if content is not None:
            chunk.content = content
        if metadata is not None:
            chunk.metadata_json = metadata
        if filename is not None:
            chunk.filename = filename

        self.db.commit()
        self.db.refresh(chunk)
        return chunk

    # DELETE
    def delete_chunk(self, chunk_id: int):
        chunk = self.get_chunk(chunk_id)
        if not chunk:
            return False
        self.db.delete(chunk)
        self.db.commit()
        return True    
    
    def get_chunks_by_filename(self, filename: str) -> List[ChunkModel]:
        return (
            self.db.query(ChunkModel)
            .filter(ChunkModel.filename == filename)
            .all()
        )
        
    def bulk_update_chunks_by_filename(
        self,
        filename: str,
        updates: list
    ) -> int:
        """
        updates = [
            { "id": 1, "content": "...", "metadata": {...} }
        ]
        """
        updated_count = 0

        for item in updates:
            chunk = (
                self.db.query(ChunkModel)
                .filter(
                    ChunkModel.id == item["id"],
                    ChunkModel.filename == filename
                )
                .first()
            )

            if not chunk:
                continue

            if item.get("content") is not None:
                chunk.content = item["content"]

            if item.get("metadata") is not None:
                chunk.metadata_json = item["metadata"]

            updated_count += 1

        self.db.commit()
        return updated_count