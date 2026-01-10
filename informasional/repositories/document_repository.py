# app/repositories/document_repository.py
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from typing import List, Optional
from informasional.models.document import Document, DocumentStatus
from datetime import datetime

class DocumentRepository:
    """
    Repository untuk database operations pada Document
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, document_data: dict) -> Document:
        """
        Create new document record
        """
        document = Document(**document_data)
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document
    
    def get_by_id(self, document_id: int) -> Optional[Document]:
        """
        Get document by ID
        """
        return self.db.query(Document).filter(Document.id == document_id).first()
    
    def get_by_filename(self, filename: str) -> Optional[Document]:
        """
        Get document by filename
        """
        return self.db.query(Document).filter(Document.filename == filename).first()
    
    def get_all(
        self, 
        skip: int = 0, 
        limit: int = 100,
        status: Optional[DocumentStatus] = None,
        order_by: str = "created_at",
        order_dir: str = "desc"
    ) -> tuple[List[Document], int]:
        """
        Get all documents with pagination and filtering
        Returns: (documents, total_count)
        """
        query = self.db.query(Document)
        
        # Filter by status
        if status:
            print(f"Filtering documents by status: {status}")
            query = query.filter(Document.status == status)
        
        # Get total count
        total = query.count()
        print(f"Total documents found: {total}")
        
        # Ordering
        order_column = getattr(Document, order_by, Document.created_at)
        if order_dir == "desc":
            query = query.order_by(desc(order_column))
        else:
            query = query.order_by(asc(order_column))
        
        # Pagination
        documents = query.offset(skip).limit(limit).all()
        print(f"Returning documents from {skip} to {skip + limit}")
        
        return documents, total
    
    
    def update(self, document_id: int, update_data: dict) -> Optional[Document]:
        """
        Update document
        """
        document = self.get_by_id(document_id)
        if not document:
            return None
        
        for key, value in update_data.items():
            setattr(document, key, value)
        
        self.db.commit()
        self.db.refresh(document)
        return document
    
    def update_status(
        self, 
        document_id: int, 
        status: DocumentStatus,
        error_message: Optional[str] = None
    ) -> Optional[Document]:
        """
        Update document status
        """
        update_data = {"status": status}
        
        if status == DocumentStatus.COMPLETED:
            update_data["processed_at"] = datetime.utcnow()
        
        if error_message:
            update_data["error_message"] = error_message
        
        return self.update(document_id, update_data)
    
    def update_extraction_results(
        self,
        document_id: int,
        raw_text: str,
        total_pages: int,
        is_scanned: bool,
        extraction_method: str,
        tables_data: List[dict],
        images_data: List[dict],
        layout_info: dict,
        ocr_confidence: Optional[float],
        extraction_duration: float
    ) -> Optional[Document]:
        """
        Update document dengan hasil ekstraksi
        """
        update_data = {
            "raw_text": raw_text,
            "text_length": len(raw_text),
            "total_pages": total_pages,
            "is_scanned": is_scanned,
            "extraction_method": extraction_method,
            "tables_data": tables_data,
            "images_data": images_data,
            "layout_info": layout_info,
            "ocr_confidence": ocr_confidence,
            "extraction_duration": extraction_duration,
            "status": DocumentStatus.COMPLETED,
            "processed_at": datetime.utcnow()
        }
        
        return self.update(document_id, update_data)
    
    def delete(self, document_id: int) -> bool:
        """
        Delete document
        """
        document = self.get_by_id(document_id)
        if not document:
            return False
        
        self.db.delete(document)
        self.db.commit()
        return True
    
    def get_statistics(self) -> dict:
        """
        Get document statistics
        """
        total = self.db.query(Document).count()
        pending = self.db.query(Document).filter(Document.status == DocumentStatus.PENDING).count()
        processing = self.db.query(Document).filter(Document.status == DocumentStatus.PROCESSING).count()
        completed = self.db.query(Document).filter(Document.status == DocumentStatus.COMPLETED).count()
        failed = self.db.query(Document).filter(Document.status == DocumentStatus.FAILED).count()
        
        return {
            "total": total,
            "pending": pending,
            "processing": processing,
            "completed": completed,
            "failed": failed
        }