import sqlite3
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from contextlib import contextmanager
import os


class DatabaseManager:
    def __init__(self, db_path: str = "data/registrations.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._init_db()
        self._run_migrations()
    
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Registrations table - support draft + user_id
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS registrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    user_id TEXT,
                    registration_number TEXT UNIQUE,
                    status TEXT DEFAULT 'draft',
                    current_step TEXT,
                    completion_percentage REAL DEFAULT 0,
                    raw_data TEXT,
                    student_data TEXT,
                    documents TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    confirmed_at TIMESTAMP,
                    expires_at TIMESTAMP
                )
            """)
            
            # Documents table - track each uploaded document
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    registration_number TEXT,
                    field_name TEXT NOT NULL,
                    file_name TEXT,
                    file_path TEXT,
                    file_size INTEGER,
                    file_type TEXT,
                    status TEXT DEFAULT 'uploaded',
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    verified_at TIMESTAMP,
                    notes TEXT,
                    FOREIGN KEY (session_id) REFERENCES registrations(session_id)
                )
            """)
            
            # Conversation logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    message TEXT,
                    metadata TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES registrations(session_id)
                )
            """)
            
            # Status history - track all status changes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS status_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    registration_number TEXT NOT NULL,
                    old_status TEXT,
                    new_status TEXT NOT NULL,
                    changed_by TEXT DEFAULT 'system',
                    notes TEXT,
                    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Migrations tracking table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    migration_name TEXT UNIQUE NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_reg_session ON registrations(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_reg_number ON registrations(registration_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_reg_status ON registrations(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_reg_user_id ON registrations(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_doc_session ON documents(session_id)")
    
    def _run_migrations(self):
        """Run pending migrations"""
        migrations = [
            ("001_add_user_id", self._migrate_add_user_id),
        ]
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            for migration_name, migration_func in migrations:
                # Check if migration already applied
                cursor.execute(
                    "SELECT id FROM migrations WHERE migration_name = ?", 
                    (migration_name,)
                )
                if cursor.fetchone() is None:
                    # Run migration
                    migration_func(cursor)
                    # Mark as applied
                    cursor.execute(
                        "INSERT INTO migrations (migration_name) VALUES (?)",
                        (migration_name,)
                    )
                    print(f"✅ Migration applied: {migration_name}")
    
    def _migrate_add_user_id(self, cursor):
        """Migration: Add user_id column to registrations table"""
        # Check if column exists
        cursor.execute("PRAGMA table_info(registrations)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'user_id' not in columns:
            cursor.execute("ALTER TABLE registrations ADD COLUMN user_id TEXT")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_reg_user_id ON registrations(user_id)")
    
    # =========================================================================
    # DRAFT MANAGEMENT
    # =========================================================================
    
    def save_draft(self, session_id: str, current_step: str, raw_data: Dict, 
                   completion_percentage: float, user_id: str = None) -> bool:
        """Save or update draft registration"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if exists
            cursor.execute("SELECT id FROM registrations WHERE session_id = ?", (session_id,))
            exists = cursor.fetchone()
            
            expires_at = (datetime.now() + timedelta(days=7)).isoformat()
            
            if exists:
                cursor.execute("""
                    UPDATE registrations SET
                        current_step = ?,
                        completion_percentage = ?,
                        raw_data = ?,
                        user_id = COALESCE(?, user_id),
                        updated_at = CURRENT_TIMESTAMP,
                        expires_at = ?
                    WHERE session_id = ?
                """, (current_step, completion_percentage, json.dumps(raw_data), 
                      user_id, expires_at, session_id))
            else:
                cursor.execute("""
                    INSERT INTO registrations 
                    (session_id, user_id, status, current_step, completion_percentage, raw_data, expires_at)
                    VALUES (?, ?, 'draft', ?, ?, ?, ?)
                """, (session_id, user_id, current_step, completion_percentage, 
                      json.dumps(raw_data), expires_at))
            
            return True
    
    def get_draft(self, session_id: str) -> Optional[Dict]:
        """Get draft by session_id"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM registrations 
                WHERE session_id = ? AND status = 'draft'
                AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            """, (session_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    "session_id": row["session_id"],
                    "user_id": row["user_id"],
                    "current_step": row["current_step"],
                    "completion_percentage": row["completion_percentage"],
                    "raw_data": json.loads(row["raw_data"]) if row["raw_data"] else {},
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                }
            return None
    
    def get_drafts_by_user(self, user_id: str) -> List[Dict]:
        """Get all drafts for a user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM registrations 
                WHERE user_id = ? AND status = 'draft'
                AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                ORDER BY updated_at DESC
            """, (user_id,))
            rows = cursor.fetchall()
            
            return [{
                "session_id": row["session_id"],
                "user_id": row["user_id"],
                "current_step": row["current_step"],
                "completion_percentage": row["completion_percentage"],
                "raw_data": json.loads(row["raw_data"]) if row["raw_data"] else {},
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            } for row in rows]
    
    # =========================================================================
    # REGISTRATION MANAGEMENT
    # =========================================================================
    
    def save_registration(self, session, registration_number: str, user_id: str = None) -> bool:
        """Convert draft to confirmed registration"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            student_data = {
                "nama_lengkap": session.get_field("nama_lengkap"),
                "nama_sekolah": session.get_field("nama_sekolah"),
                "tingkatan": session.get_field("tingkatan"),
                "program": session.get_field("program"),
                "tempat_lahir": session.get_field("tempat_lahir"),
                "tanggal_lahir": session.get_field("tanggal_lahir"),
                "jenis_kelamin": session.get_field("jenis_kelamin"),
            }
            
            # Check if draft exists
            cursor.execute("SELECT id, user_id FROM registrations WHERE session_id = ?", 
                          (session.session_id,))
            exists = cursor.fetchone()
            
            # Use existing user_id if not provided
            final_user_id = user_id or (exists["user_id"] if exists else None)
            
            if exists:
                cursor.execute("""
                    UPDATE registrations SET
                        registration_number = ?,
                        user_id = COALESCE(?, user_id),
                        status = 'pending_payment',
                        raw_data = ?,
                        student_data = ?,
                        confirmed_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE session_id = ?
                """, (registration_number, final_user_id, json.dumps(session.raw_data),
                      json.dumps(student_data), session.session_id))
            else:
                cursor.execute("""
                    INSERT INTO registrations 
                    (session_id, user_id, registration_number, status, current_step, 
                     completion_percentage, raw_data, student_data, confirmed_at)
                    VALUES (?, ?, ?, 'pending_payment', ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (session.session_id, final_user_id, registration_number, session.current_step,
                      100, json.dumps(session.raw_data), json.dumps(student_data)))
            
            # Update documents with registration number
            cursor.execute("""
                UPDATE documents SET registration_number = ?
                WHERE session_id = ?
            """, (registration_number, session.session_id))
            
            # Log status change
            self._log_status_change(cursor, registration_number, None, 'pending_payment', 
                                   'system', 'Pendaftaran dikonfirmasi')
            
            return True
    
    def get_registration(self, registration_number: str) -> Optional[Dict]:
        """Get registration by registration number"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM registrations WHERE registration_number = ?
            """, (registration_number,))
            row = cursor.fetchone()
            
            if row:
                # Get documents
                cursor.execute("""
                    SELECT * FROM documents WHERE registration_number = ?
                    ORDER BY uploaded_at
                """, (registration_number,))
                docs = cursor.fetchall()
                
                # Get status history
                cursor.execute("""
                    SELECT * FROM status_history WHERE registration_number = ?
                    ORDER BY changed_at DESC
                """, (registration_number,))
                history = cursor.fetchall()
                
                return {
                    "registration_number": row["registration_number"],
                    "session_id": row["session_id"],
                    "user_id": row["user_id"],
                    "status": row["status"],
                    "current_step": row["current_step"],
                    "completion_percentage": row["completion_percentage"],
                    "raw_data": json.loads(row["raw_data"]) if row["raw_data"] else {},
                    "student_data": json.loads(row["student_data"]) if row["student_data"] else {},
                    "documents": [dict(d) for d in docs],
                    "status_history": [dict(h) for h in history],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "confirmed_at": row["confirmed_at"]
                }
            return None
    
    def get_registration_by_session(self, session_id: str) -> Optional[Dict]:
        """Get registration by session ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM registrations WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    "registration_number": row["registration_number"],
                    "session_id": row["session_id"],
                    "user_id": row["user_id"],
                    "status": row["status"],
                    "current_step": row["current_step"],
                    "completion_percentage": row["completion_percentage"],
                    "raw_data": json.loads(row["raw_data"]) if row["raw_data"] else {},
                    "student_data": json.loads(row["student_data"]) if row["student_data"] else {},
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                }
            return None
    
    def get_registrations_by_user(self, user_id: str, status: str = None) -> List[Dict]:
        """Get all registrations for a user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if status:
                cursor.execute("""
                    SELECT * FROM registrations 
                    WHERE user_id = ? AND status = ?
                    ORDER BY updated_at DESC
                """, (user_id, status))
            else:
                cursor.execute("""
                    SELECT * FROM registrations 
                    WHERE user_id = ?
                    ORDER BY updated_at DESC
                """, (user_id,))
            
            rows = cursor.fetchall()
            
            return [{
                "registration_number": row["registration_number"],
                "session_id": row["session_id"],
                "user_id": row["user_id"],
                "status": row["status"],
                "current_step": row["current_step"],
                "completion_percentage": row["completion_percentage"],
                "raw_data": json.loads(row["raw_data"]) if row["raw_data"] else {},
                "student_data": json.loads(row["student_data"]) if row["student_data"] else {},
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "confirmed_at": row["confirmed_at"]
            } for row in rows]
    
    def update_registration_status(self, registration_number: str, status: str, 
                                   notes: str = None, changed_by: str = "system") -> bool:
        """Update registration status with history"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get current status
            cursor.execute("SELECT status FROM registrations WHERE registration_number = ?",
                          (registration_number,))
            row = cursor.fetchone()
            if not row:
                return False
            
            old_status = row["status"]
            
            # Update status
            cursor.execute("""
                UPDATE registrations SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE registration_number = ?
            """, (status, registration_number))
            
            # Log status change
            self._log_status_change(cursor, registration_number, old_status, status, 
                                   changed_by, notes)
            
            return True
    
    def update_registration_user(self, session_id: str, user_id: str) -> bool:
        """Update user_id for a registration"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE registrations SET user_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
            """, (user_id, session_id))
            return cursor.rowcount > 0
    
    def _log_status_change(self, cursor, registration_number: str, old_status: str,
                          new_status: str, changed_by: str, notes: str):
        """Log status change to history"""
        cursor.execute("""
            INSERT INTO status_history 
            (registration_number, old_status, new_status, changed_by, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (registration_number, old_status, new_status, changed_by, notes))
    
    # =========================================================================
    # DOCUMENT MANAGEMENT
    # =========================================================================
    
    def save_document(self, session_id: str, field_name: str, file_name: str,
                     file_path: str, file_size: int, file_type: str,
                     registration_number: str = None) -> int:
        """Save uploaded document"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if document for this field already exists
            cursor.execute("""
                SELECT id FROM documents 
                WHERE session_id = ? AND field_name = ?
            """, (session_id, field_name))
            exists = cursor.fetchone()
            
            if exists:
                cursor.execute("""
                    UPDATE documents SET
                        file_name = ?, file_path = ?, file_size = ?,
                        file_type = ?, uploaded_at = CURRENT_TIMESTAMP, status = 'uploaded'
                    WHERE session_id = ? AND field_name = ?
                """, (file_name, file_path, file_size, file_type, session_id, field_name))
                return exists["id"]
            else:
                cursor.execute("""
                    INSERT INTO documents 
                    (session_id, registration_number, field_name, file_name, 
                     file_path, file_size, file_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (session_id, registration_number, field_name, file_name,
                      file_path, file_size, file_type))
                return cursor.lastrowid
    
    def get_documents(self, session_id: str = None, registration_number: str = None) -> List[Dict]:
        """Get documents by session or registration number"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if registration_number:
                cursor.execute("""
                    SELECT * FROM documents WHERE registration_number = ?
                    ORDER BY uploaded_at
                """, (registration_number,))
            elif session_id:
                cursor.execute("""
                    SELECT * FROM documents WHERE session_id = ?
                    ORDER BY uploaded_at
                """, (session_id,))
            else:
                return []
            
            return [dict(row) for row in cursor.fetchall()]
    
    def update_document_status(self, doc_id: int, status: str, notes: str = None) -> bool:
        """Update document verification status"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE documents SET 
                    status = ?, notes = ?,
                    verified_at = CASE WHEN ? = 'verified' THEN CURRENT_TIMESTAMP ELSE verified_at END
                WHERE id = ?
            """, (status, notes, status, doc_id))
            return cursor.rowcount > 0
    
    # =========================================================================
    # CONVERSATION LOGGING
    # =========================================================================
    
    def log_conversation(self, session_id: str, role: str, message: str, 
                        metadata: Dict = None):
        """Log conversation message"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO conversation_logs (session_id, role, message, metadata)
                VALUES (?, ?, ?, ?)
            """, (session_id, role, message, json.dumps(metadata) if metadata else None))
    
    def get_conversation_history(self, session_id: str, limit: int = 50) -> List[Dict]:
        """Get conversation history"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM conversation_logs 
                WHERE session_id = ?
                ORDER BY timestamp DESC LIMIT ?
            """, (session_id, limit))
            return [dict(row) for row in cursor.fetchall()][::-1]
    
    # =========================================================================
    # TRACKING & STATISTICS
    # =========================================================================
    
    def get_registration_stats(self, user_id: str = None) -> Dict:
        """Get registration statistics, optionally filtered by user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            user_filter = "WHERE user_id = ?" if user_id else ""
            params = (user_id,) if user_id else ()
            
            # Count by status
            cursor.execute(f"""
                SELECT status, COUNT(*) as count FROM registrations
                {user_filter}
                GROUP BY status
            """, params)
            status_counts = {row["status"]: row["count"] for row in cursor.fetchall()}
            
            # Today's registrations
            if user_id:
                cursor.execute("""
                    SELECT COUNT(*) as count FROM registrations
                    WHERE user_id = ? AND DATE(created_at) = DATE('now')
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT COUNT(*) as count FROM registrations
                    WHERE DATE(created_at) = DATE('now')
                """)
            today = cursor.fetchone()["count"]
            
            # This week
            if user_id:
                cursor.execute("""
                    SELECT COUNT(*) as count FROM registrations
                    WHERE user_id = ? AND created_at >= DATE('now', '-7 days')
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT COUNT(*) as count FROM registrations
                    WHERE created_at >= DATE('now', '-7 days')
                """)
            this_week = cursor.fetchone()["count"]
            
            return {
                "by_status": status_counts,
                "today": today,
                "this_week": this_week,
                "total": sum(status_counts.values())
            }
    
    def cleanup_expired_drafts(self) -> int:
        """Remove expired draft registrations"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM registrations 
                WHERE status = 'draft' AND expires_at < CURRENT_TIMESTAMP
            """)
            return cursor.rowcount


# Singleton
_db_manager: Optional[DatabaseManager] = None

def get_db_manager() -> DatabaseManager:
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager

def init_database():
    """Initialize database"""
    return get_db_manager()