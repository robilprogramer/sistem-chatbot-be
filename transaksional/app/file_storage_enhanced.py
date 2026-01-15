"""
Enhanced File Storage - Multiple File Upload Support
=====================================================
Features:
- Upload multiple files sekaligus
- Batch tracking
- Progress tracking
- File organization by batch
"""

import os
import uuid
import shutil
import asyncio
from datetime import datetime
from typing import Optional, Tuple, Dict, List, Any
from pathlib import Path
import mimetypes
from dataclasses import dataclass, field
from enum import Enum


class FileValidationError(Exception):
    """Custom exception for file validation errors"""
    def __init__(self, message: str, error_type: str = "validation", file_name: str = None):
        self.message = message
        self.error_type = error_type
        self.file_name = file_name
        super().__init__(self.message)


class UploadStatus(str, Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # Some files failed


@dataclass
class FileUploadResult:
    """Result for single file upload"""
    success: bool
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    original_name: Optional[str] = None
    file_size: int = 0
    file_type: Optional[str] = None
    content_type: Optional[str] = None
    extension: Optional[str] = None
    error: Optional[str] = None
    order: int = 0


@dataclass
class BatchUploadResult:
    """Result for batch upload"""
    batch_id: str
    status: UploadStatus
    total_files: int
    successful_files: int
    failed_files: int
    results: List[FileUploadResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "status": self.status.value,
            "total_files": self.total_files,
            "successful_files": self.successful_files,
            "failed_files": self.failed_files,
            "results": [
                {
                    "success": r.success,
                    "file_name": r.file_name,
                    "original_name": r.original_name,
                    "file_size": r.file_size,
                    "error": r.error,
                    "order": r.order
                }
                for r in self.results
            ],
            "errors": self.errors
        }


class EnhancedFileStorage:
    """
    Enhanced file storage with multiple file upload support.
    """
    
    # Allowed MIME types per document type
    ALLOWED_TYPES = {
        "image": ["image/jpeg", "image/png", "image/gif", "image/webp"],
        "pdf": ["application/pdf"],
        "document": [
            "application/pdf",
            "image/jpeg", 
            "image/png",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ]
    }
    
    # Max sizes in bytes
    MAX_SIZES = {
        "foto_siswa": 2 * 1024 * 1024,      # 2MB for photos
        "rapor_terakhir": 10 * 1024 * 1024,  # 10MB for rapor
        "batch": 50 * 1024 * 1024,           # 50MB total for batch
        "default": 5 * 1024 * 1024           # 5MB default
    }
    
    # Max files per batch
    MAX_FILES_PER_BATCH = 10
    
    # Allowed extensions per field
    FIELD_EXTENSIONS = {
        "foto_siswa": [".jpg", ".jpeg", ".png"],
        "akta_kelahiran": [".pdf", ".jpg", ".jpeg", ".png"],
        "kartu_keluarga": [".pdf", ".jpg", ".jpeg", ".png"],
        "ijazah_terakhir": [".pdf", ".jpg", ".jpeg", ".png"],
        "rapor_terakhir": [".pdf", ".jpg", ".jpeg", ".png"],
        "ktp_ortu": [".pdf", ".jpg", ".jpeg", ".png"],
        "bukti_pembayaran": [".pdf", ".jpg", ".jpeg", ".png"],
        "default": [".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"]
    }
    
    def __init__(self, base_path: str = "uploads", db_manager=None):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._db = db_manager
    
    @property
    def db(self):
        if self._db is None:
            try:
                from transaksional.app.database import get_db_manager
                self._db = get_db_manager()
            except:
                pass
        return self._db
    
    def validate_file(self, file, field_name: str) -> Tuple[bool, Optional[str], Dict]:
        """
        Validate uploaded file
        Returns: (is_valid, error_message, metadata)
        """
        metadata = {
            "original_name": getattr(file, 'filename', 'unknown'),
            "size": 0,
            "content_type": getattr(file, 'content_type', None),
            "extension": ""
        }
        
        # Check filename
        if not file.filename:
            return False, "Nama file tidak valid", metadata
        
        # Get extension
        ext = Path(file.filename).suffix.lower()
        metadata["extension"] = ext
        
        # Check allowed extensions
        allowed_ext = self.FIELD_EXTENSIONS.get(field_name, self.FIELD_EXTENSIONS["default"])
        if ext not in allowed_ext:
            return False, f"Format file tidak didukung. Format yang diizinkan: {', '.join(allowed_ext)}", metadata
        
        # Check MIME type
        content_type = file.content_type or mimetypes.guess_type(file.filename)[0]
        metadata["content_type"] = content_type
        
        # Check file size
        file.file.seek(0, 2)  # Seek to end
        size = file.file.tell()
        file.file.seek(0)  # Reset
        metadata["size"] = size
        
        max_size = self.MAX_SIZES.get(field_name, self.MAX_SIZES["default"])
        if size > max_size:
            max_mb = max_size / (1024 * 1024)
            size_mb = size / (1024 * 1024)
            return False, f"File terlalu besar ({size_mb:.1f}MB). Maksimal {max_mb:.0f}MB", metadata
        
        if size == 0:
            return False, "File kosong", metadata
        
        return True, None, metadata
    
    async def save_single_file(self, file, session_id: str, file_type: str,
                               registration_number: str = None,
                               batch_id: str = None,
                               order: int = 0) -> FileUploadResult:
        """
        Save single uploaded file with validation
        """
        # Validate
        is_valid, error, metadata = self.validate_file(file, file_type)
        
        if not is_valid:
            return FileUploadResult(
                success=False,
                original_name=metadata["original_name"],
                error=error,
                order=order
            )
        
        # Create directory structure
        if registration_number:
            dir_path = self.base_path / registration_number
        elif batch_id:
            dir_path = self.base_path / "batches" / batch_id
        else:
            dir_path = self.base_path / "sessions" / session_id
        
        dir_path.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        safe_name = f"{file_type}_{order:02d}_{timestamp}_{unique_id}{metadata['extension']}"
        
        file_path = dir_path / safe_name
        
        # Save file
        try:
            content = await file.read()
            with open(file_path, "wb") as buffer:
                buffer.write(content)
            
            # Save to database if available
            if self.db:
                try:
                    self.db.save_document(
                        session_id=session_id,
                        field_name=file_type,
                        file_name=safe_name,
                        file_path=str(file_path),
                        file_size=metadata["size"],
                        file_type=metadata["content_type"],
                        registration_number=registration_number,
                        batch_id=batch_id,
                        file_order=order
                    )
                except Exception as e:
                    print(f"Warning: Could not save to DB: {e}")
            
            return FileUploadResult(
                success=True,
                file_path=str(file_path),
                file_name=safe_name,
                original_name=metadata["original_name"],
                file_size=metadata["size"],
                file_type=file_type,
                content_type=metadata["content_type"],
                extension=metadata["extension"],
                order=order
            )
            
        except Exception as e:
            return FileUploadResult(
                success=False,
                original_name=metadata["original_name"],
                error=f"Gagal menyimpan file: {str(e)}",
                order=order
            )
    
    async def save_multiple_files(self, files: List, session_id: str, file_type: str,
                                  registration_number: str = None) -> BatchUploadResult:
        """
        Save multiple files at once with batch tracking
        """
        batch_id = str(uuid.uuid4())
        
        # Validate batch size
        if len(files) > self.MAX_FILES_PER_BATCH:
            return BatchUploadResult(
                batch_id=batch_id,
                status=UploadStatus.FAILED,
                total_files=len(files),
                successful_files=0,
                failed_files=len(files),
                errors=[f"Maksimal {self.MAX_FILES_PER_BATCH} file per upload"]
            )
        
        # Filter out empty files
        valid_files = [f for f in files if f and f.filename]
        
        if not valid_files:
            return BatchUploadResult(
                batch_id=batch_id,
                status=UploadStatus.FAILED,
                total_files=0,
                successful_files=0,
                failed_files=0,
                errors=["Tidak ada file yang valid"]
            )
        
        # Calculate total size
        total_size = 0
        for f in valid_files:
            f.file.seek(0, 2)
            total_size += f.file.tell()
            f.file.seek(0)
        
        max_batch_size = self.MAX_SIZES.get("batch", 50 * 1024 * 1024)
        if total_size > max_batch_size:
            max_mb = max_batch_size / (1024 * 1024)
            total_mb = total_size / (1024 * 1024)
            return BatchUploadResult(
                batch_id=batch_id,
                status=UploadStatus.FAILED,
                total_files=len(valid_files),
                successful_files=0,
                failed_files=len(valid_files),
                errors=[f"Total ukuran file ({total_mb:.1f}MB) melebihi batas ({max_mb:.0f}MB)"]
            )
        
        # Create batch record in DB
        if self.db:
            try:
                self.db.create_upload_batch(
                    batch_id=batch_id,
                    session_id=session_id,
                    field_name=file_type,
                    total_files=len(valid_files)
                )
            except Exception as e:
                print(f"Warning: Could not create batch record: {e}")
        
        # Upload files concurrently
        results = []
        tasks = []
        
        for i, file in enumerate(valid_files):
            task = self.save_single_file(
                file=file,
                session_id=session_id,
                file_type=file_type,
                registration_number=registration_number,
                batch_id=batch_id,
                order=i
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # Calculate stats
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        errors = [r.error for r in results if r.error]
        
        # Determine status
        if successful == 0:
            status = UploadStatus.FAILED
        elif failed > 0:
            status = UploadStatus.PARTIAL
        else:
            status = UploadStatus.COMPLETED
        
        # Update batch record
        if self.db:
            try:
                self.db.update_upload_batch(
                    batch_id=batch_id,
                    uploaded_files=successful,
                    status=status.value
                )
            except Exception as e:
                print(f"Warning: Could not update batch record: {e}")
        
        return BatchUploadResult(
            batch_id=batch_id,
            status=status,
            total_files=len(valid_files),
            successful_files=successful,
            failed_files=failed,
            results=list(results),
            errors=errors
        )
    
    def get_batch_files(self, batch_id: str) -> List[Dict]:
        """Get all files in a batch"""
        batch_path = self.base_path / "batches" / batch_id
        if not batch_path.exists():
            return []
        
        files = []
        for file_path in sorted(batch_path.iterdir()):
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "file_path": str(file_path),
                    "file_name": file_path.name,
                    "size": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat()
                })
        
        return files
    
    def get_session_files(self, session_id: str, field_name: str = None) -> List[Dict]:
        """Get all files for a session, optionally filtered by field"""
        session_path = self.base_path / "sessions" / session_id
        if not session_path.exists():
            return []
        
        files = []
        for file_path in sorted(session_path.iterdir()):
            if file_path.is_file():
                # Filter by field name if specified
                if field_name and not file_path.name.startswith(field_name):
                    continue
                
                stat = file_path.stat()
                files.append({
                    "file_path": str(file_path),
                    "file_name": file_path.name,
                    "size": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat()
                })
        
        return files
    
    def move_batch_to_registration(self, batch_id: str, registration_number: str) -> int:
        """Move batch files to registration folder"""
        source = self.base_path / "batches" / batch_id
        dest = self.base_path / registration_number
        
        if not source.exists():
            return 0
        
        dest.mkdir(parents=True, exist_ok=True)
        
        count = 0
        for file_path in source.iterdir():
            if file_path.is_file():
                shutil.move(str(file_path), str(dest / file_path.name))
                count += 1
        
        # Remove empty batch folder
        try:
            source.rmdir()
        except:
            pass
        
        return count
    
    def delete_batch(self, batch_id: str) -> bool:
        """Delete entire batch"""
        batch_path = self.base_path / "batches" / batch_id
        if batch_path.exists():
            shutil.rmtree(str(batch_path))
            return True
        return False
    
    def get_file_info(self, file_path: str) -> Optional[Dict]:
        """Get file information"""
        path = Path(file_path)
        if not path.exists():
            return None
        
        stat = path.stat()
        return {
            "file_path": str(path),
            "file_name": path.name,
            "size": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
        }
    
    def delete_file(self, file_path: str) -> bool:
        """Delete a file"""
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                return True
            return False
        except Exception:
            return False
    
    def cleanup_old_batches(self, days: int = 1) -> int:
        """Clean up old incomplete batches"""
        batches_path = self.base_path / "batches"
        if not batches_path.exists():
            return 0
        
        cutoff = datetime.now().timestamp() - (days * 24 * 60 * 60)
        count = 0
        
        for batch_dir in batches_path.iterdir():
            if batch_dir.is_dir():
                # Check if all files are older than cutoff
                all_old = True
                for file_path in batch_dir.iterdir():
                    if file_path.stat().st_mtime > cutoff:
                        all_old = False
                        break
                
                if all_old:
                    shutil.rmtree(str(batch_dir))
                    count += 1
        
        return count


# =============================================================================
# SINGLETON
# =============================================================================

_file_storage: Optional[EnhancedFileStorage] = None

def get_file_storage() -> EnhancedFileStorage:
    global _file_storage
    if _file_storage is None:
        _file_storage = EnhancedFileStorage()
    return _file_storage