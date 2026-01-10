
import os
import uuid
from pathlib import Path
from typing import Optional
from fastapi import UploadFile
from sqlalchemy.orm import Session
from datetime import datetime
from informasional.models.document import DocumentStatus,ExtractionMethod
from informasional.repositories.document_repository import DocumentRepository
from informasional.services.pdf_to_knowledge import PDFToKnowledgeConverter

class DocumentService:
    
    def __init__(self, db: Session, upload_dir: str = "./uploads"):
        self.db = db
        self.repository = DocumentRepository(db)
        openai_key = os.getenv("OPENAI_API_KEY")
        openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.converter = PDFToKnowledgeConverter(
            openai_api_key=openai_key,
            model=openai_model
        )
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
    
    async def upload_document(self, file: UploadFile) -> dict:
        """
        Upload dan save file, create document record
        """
        # Validate file type
        if not file.filename.endswith('.pdf'):
            raise ValueError("Only PDF files are allowed")
        
        # Generate unique filename
        file_ext = Path(file.filename).suffix
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = self.upload_dir / unique_filename
        
        # Save file
        file_size = 0
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
            file_size = len(content)
        
        # Create document record
        document_data = {
            "filename": unique_filename,
            "original_filename": file.filename,
            "file_path": str(file_path),
            "file_size": file_size,
            "mime_type": file.content_type or "application/pdf",
            "status": DocumentStatus.PENDING
        }
        
        document = self.repository.create(document_data)
        
        return {
            "document_id": document.id,
            "filename": document.filename,
            "original_filename": document.original_filename,
            "status": document.status
        }
    
    def process_document(self, document_id: int) -> dict:
        """
        Process document: PDF → AI Knowledge Base
        """
        # Get document
        document = self.repository.get_by_id(document_id)
        if not document:
            raise ValueError(f"Document {document_id} not found")
        
        if document.status != DocumentStatus.PENDING:
            raise ValueError(f"Document {document_id} is already {document.status}")
        
        try:
            # Update to processing
            self.repository.update_status(document_id, DocumentStatus.PROCESSING)
            
            print(f"🚀 Processing document {document_id}...")
            
            # ✅ Convert PDF to Knowledge Base
            result = self.converter.process(
                pdf_path=document.file_path,
                doc_title=document.original_filename
            )
            
            print(result.raw_text[:500])  # Print preview of raw text
            print("✅ Conversion completed!")
            
            # Update document with results
            updated_doc = self.repository.update_extraction_results(
                document_id=document_id,
                raw_text=result.knowledge_text,  # ✅ AI-generated knowledge
                total_pages=result.total_pages,
                is_scanned=False,  # Not relevant anymore
                extraction_method=ExtractionMethod.NATIVE,
                tables_data=[],  # Tables already explained in knowledge text
                images_data=[],
                layout_info={
                    "total_pages": result.total_pages,
                    "has_tables": result.has_tables,
                    "ai_model": result.ai_model,
                    "original_length": result.original_length,
                    "knowledge_length": result.knowledge_length
                },
                ocr_confidence=None,
                extraction_duration=result.processing_duration,
                raw_text_original=result.raw_text
            )
            
            return {
                "success": True,
                "document_id": updated_doc.id,
                "raw_text_preview": result.knowledge_text[:500],
                "total_pages": result.total_pages,
                "text_length": len(result.knowledge_text),
                "tables_count": 0,
                "images_count": 0,
                "ai_model": result.ai_model
            }
        
        except Exception as e:
            # Update to failed
            self.repository.update_status(
                document_id, 
                DocumentStatus.FAILED,
                error_message=str(e)
            )
            raise e
    
    
    def get_document(self, document_id: int):
        """Get document by ID"""
        return self.repository.get_by_id(document_id)
    
    def get_documents(self, skip: int = 0, limit: int = 100, status: Optional[str] = None):
        """Get all documents with pagination"""
        status_enum = DocumentStatus(status) if status else None
        print(f"Fetching documents with status: {status_enum}")
        
        return self.repository.get_all(skip=skip, limit=limit, status=status_enum)
    
    def delete_document(self, document_id: int) -> bool:
        """Delete document dan file-nya"""
        document = self.repository.get_by_id(document_id)
        if not document:
            return False
        
        # Delete file
        try:
            if os.path.exists(document.file_path):
                os.remove(document.file_path)
        except Exception as e:
            print(f"Error deleting file: {e}")
        
        # Delete from database
        return self.repository.delete(document_id)
    
    
    def update_raw_text(self, document_id: int, raw_text: str):
        
        print(f"Updating raw_text for document {document_id}...")
        print(f"New raw_text length: {len(raw_text)} characters")
        document = self.repository.get_by_id(document_id)
        if not document:
            raise ValueError("Document not found")

        document.raw_text = raw_text
        document.text_length = len(raw_text)
        document.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(document)
        return document