"""
File Storage - Document Upload with Validation
===============================================
- Validate file type, size, format
- Organize by session/registration
- Visual feedback support
"""

import os
import uuid
import shutil
from datetime import datetime
from typing import Optional, Tuple, Dict, List
from pathlib import Path
import mimetypes


class FileValidationError(Exception):
    """Custom exception for file validation errors"""
    def __init__(self, message: str, error_type: str = "validation"):
        self.message = message
        self.error_type = error_type
        super().__init__(self.message)


class FileStorage:
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
        "default": 5 * 1024 * 1024           # 5MB default
    }
    
    # Allowed extensions per field
    FIELD_EXTENSIONS = {
        "foto_siswa": [".jpg", ".jpeg", ".png"],
        "akta_kelahiran": [".pdf", ".jpg", ".jpeg", ".png"],
        "kartu_keluarga": [".pdf", ".jpg", ".jpeg", ".png"],
        "ijazah_terakhir": [".pdf", ".jpg", ".jpeg", ".png"],
        "rapor_terakhir": [".pdf", ".jpg", ".jpeg", ".png"],
        "ktp_ortu": [".pdf", ".jpg", ".jpeg", ".png"],
        "default": [".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"]
    }
    
    def __init__(self, base_path: str = "uploads"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def validate_file(self, file, field_name: str) -> Tuple[bool, Optional[str], Dict]:
        """
        Validate uploaded file
        Returns: (is_valid, error_message, metadata)
        """
        metadata = {
            "original_name": file.filename,
            "size": 0,
            "content_type": file.content_type,
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
        allowed_mimes = self.ALLOWED_TYPES.get("document", [])
        if content_type and content_type not in allowed_mimes:
            # Allow if extension is correct even if MIME is wrong
            pass
        
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
    
    async def save_file(self, file, session_id: str, file_type: str, 
                        registration_number: str = None) -> Dict:
        """
        Save uploaded file with validation
        Returns dict with file info or raises FileValidationError
        """
        # Validate
        is_valid, error, metadata = self.validate_file(file, file_type)
        
        if not is_valid:
            raise FileValidationError(error, "validation")
        
        # Create directory structure
        if registration_number:
            dir_path = self.base_path / registration_number
        else:
            dir_path = self.base_path / "sessions" / session_id
        
        dir_path.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        safe_name = f"{file_type}_{timestamp}_{unique_id}{metadata['extension']}"
        
        file_path = dir_path / safe_name
        
        # Save file
        try:
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
        except Exception as e:
            raise FileValidationError(f"Gagal menyimpan file: {str(e)}", "storage")
        
        return {
            "success": True,
            "file_path": str(file_path),
            "file_name": safe_name,
            "original_name": metadata["original_name"],
            "file_size": metadata["size"],
            "file_type": file_type,
            "content_type": metadata["content_type"],
            "extension": metadata["extension"]
        }
    
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
    
    def list_files(self, session_id: str = None, registration_number: str = None) -> List[Dict]:
        """List files for a session or registration"""
        if registration_number:
            dir_path = self.base_path / registration_number
        elif session_id:
            dir_path = self.base_path / "sessions" / session_id
        else:
            return []
        
        if not dir_path.exists():
            return []
        
        files = []
        for file_path in dir_path.iterdir():
            if file_path.is_file():
                files.append(self.get_file_info(str(file_path)))
        
        return files
    
    def move_to_registration(self, session_id: str, registration_number: str) -> int:
        """Move session files to registration folder"""
        source = self.base_path / "sessions" / session_id
        dest = self.base_path / registration_number
        
        if not source.exists():
            return 0
        
        dest.mkdir(parents=True, exist_ok=True)
        
        count = 0
        for file_path in source.iterdir():
            if file_path.is_file():
                shutil.move(str(file_path), str(dest / file_path.name))
                count += 1
        
        # Remove empty session folder
        try:
            source.rmdir()
        except:
            pass
        
        return count
    
    def cleanup_old_sessions(self, days: int = 7) -> int:
        """Clean up old session files"""
        sessions_path = self.base_path / "sessions"
        if not sessions_path.exists():
            return 0
        
        cutoff = datetime.now().timestamp() - (days * 24 * 60 * 60)
        count = 0
        
        for session_dir in sessions_path.iterdir():
            if session_dir.is_dir():
                # Check if all files are older than cutoff
                all_old = True
                for file_path in session_dir.iterdir():
                    if file_path.stat().st_mtime > cutoff:
                        all_old = False
                        break
                
                if all_old:
                    shutil.rmtree(str(session_dir))
                    count += 1
        
        return count


# Singleton
_file_storage: Optional[FileStorage] = None

def get_file_storage() -> FileStorage:
    global _file_storage
    if _file_storage is None:
        _file_storage = FileStorage()
    return _file_storage
