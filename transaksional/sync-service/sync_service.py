"""
Sync Service - SQLite to PostgreSQL
====================================
Background process untuk sync data dari SQLite (chatbot) ke PostgreSQL (production)

Bisa dijalankan sebagai:
1. Scheduler (cron job / APScheduler)
2. Manual trigger dari admin
3. Event-driven setelah registration confirmed

PostgreSQL Schema Target:
- student_registrations
- registration_documents  
- registration_tracking
- conversations
- conversation_state
"""

import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager
import os
from pathlib import Path
# Load .env file
from dotenv import load_dotenv

# Cari .env dari root project (backend/)
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

print(f"📂 Loading .env from: {env_path}")
print(f"📂 .env exists: {env_path.exists()}")
print(f"📂 DATABASE_URL: {os.getenv('DATABASE_URL', 'NOT FOUND')}")


# PostgreSQL
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor, Json
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False
    print("⚠️ psycopg2 not installed. Run: pip install psycopg2-binary")


class SyncService:
    """
    Service untuk sync data dari SQLite ke PostgreSQL
    
    SQLite Tables (Source):
    - registrations
    - documents
    - conversation_logs
    - status_history
    
    PostgreSQL Tables (Target):
    - student_registrations
    - registration_documents
    - registration_tracking
    - conversations
    - conversation_state
    """
    
    def __init__(self, sqlite_path: str = None, 
                 postgres_url: str = None):
         # Auto-resolve path ke backend/data/registrations.db
        if sqlite_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            sqlite_path = os.path.join(project_root, "data", "registrations.db")
        
        self.sqlite_path = sqlite_path
        self.postgres_url = postgres_url or os.getenv(
                "DATABASE_URL", 
                "postgresql://admin:admin123@localhost:5432/xxxxx"
            )
        self.sync_log = []
    
    # =========================================================================
    # CONNECTION MANAGERS
    # =========================================================================
    
    @contextmanager
    def get_sqlite_conn(self):
        """Get SQLite connection"""
        print(f"🔗 Connecting to SQLite DB at: {self.sqlite_path}")
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    @contextmanager
    def get_postgres_conn(self):
        """Get PostgreSQL connection"""
        if not HAS_POSTGRES:
            raise Exception("psycopg2 not installed")
        
        conn = psycopg2.connect(self.postgres_url)
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    # =========================================================================
    # INIT POSTGRES TABLES (if not exists)
    # =========================================================================
    
    def init_postgres_tables(self):
        """Create PostgreSQL tables if not exists"""
        with self.get_postgres_conn() as conn:
            cursor = conn.cursor()
            
            # student_registrations
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS student_registrations (
                    id SERIAL PRIMARY KEY,
                    registration_number VARCHAR(20) UNIQUE NOT NULL,
                    student_data JSONB,
                    parent_data JSONB,
                    academic_data JSONB,
                    status VARCHAR(50) DEFAULT 'pending_payment',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # registration_documents
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS registration_documents (
                    id SERIAL PRIMARY KEY,
                    registration_id INTEGER REFERENCES student_registrations(id) ON DELETE CASCADE,
                    document_type VARCHAR(50) NOT NULL,
                    filename VARCHAR(255),
                    file_path TEXT,
                    status VARCHAR(50) DEFAULT 'uploaded',
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # registration_tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS registration_tracking (
                    id SERIAL PRIMARY KEY,
                    registration_id INTEGER REFERENCES student_registrations(id) ON DELETE CASCADE,
                    status VARCHAR(100) NOT NULL,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # conversations
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(100) NOT NULL,
                    user_message TEXT,
                    bot_response TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # conversation_state
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_state (
                    session_id VARCHAR(100) PRIMARY KEY,
                    current_step VARCHAR(50),
                    collected_data JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sr_reg_number ON student_registrations(registration_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sr_status ON student_registrations(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_rd_reg_id ON registration_documents(registration_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_rt_reg_id ON registration_tracking(registration_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id)")
            
            print("✅ PostgreSQL tables initialized")
    
    # =========================================================================
    # DATA TRANSFORMATION / MAPPING
    # =========================================================================
    
    def _transform_registration(self, sqlite_row: dict) -> Dict[str, Any]:
        """
        Transform SQLite registration to PostgreSQL format
        
        SQLite: raw_data (semua data dalam 1 JSON)
        PostgreSQL: student_data, parent_data, academic_data (terpisah)
        """
        raw_data = json.loads(sqlite_row["raw_data"]) if sqlite_row["raw_data"] else {}
        
        # Extract student data
        student_data = {
            "nama_lengkap": raw_data.get("nama_lengkap"),
            "nama_panggilan": raw_data.get("nama_panggilan"),
            "tempat_lahir": raw_data.get("tempat_lahir"),
            "tanggal_lahir": raw_data.get("tanggal_lahir"),
            "jenis_kelamin": raw_data.get("jenis_kelamin"),
            "agama": raw_data.get("agama"),
            "alamat": raw_data.get("alamat"),
            "no_telepon": raw_data.get("no_telepon"),
            "email": raw_data.get("email"),
            "nama_sekolah": raw_data.get("nama_sekolah"),
            "tingkatan": raw_data.get("tingkatan"),
            "program": raw_data.get("program"),
        }
        
        # Extract parent data
        parent_data = {
            "nama_ayah": raw_data.get("nama_ayah"),
            "pekerjaan_ayah": raw_data.get("pekerjaan_ayah"),
            "no_telepon_ayah": raw_data.get("no_telepon_ayah"),
            "nama_ibu": raw_data.get("nama_ibu"),
            "pekerjaan_ibu": raw_data.get("pekerjaan_ibu"),
            "no_telepon_ibu": raw_data.get("no_telepon_ibu"),
        }
        
        # Extract academic data
        academic_data = {
            "nama_sekolah_asal": raw_data.get("nama_sekolah_asal"),
            "alamat_sekolah_asal": raw_data.get("alamat_sekolah_asal"),
            "tahun_lulus": raw_data.get("tahun_lulus"),
            "nilai_rata_rata": raw_data.get("nilai_rata_rata"),
            "nilai_matematika": raw_data.get("nilai_matematika"),
            "nilai_bahasa_indonesia": raw_data.get("nilai_bahasa_indonesia"),
            "nilai_bahasa_inggris": raw_data.get("nilai_bahasa_inggris"),
            "nilai_ipa": raw_data.get("nilai_ipa"),
            "prestasi_akademik": raw_data.get("prestasi_akademik"),
        }
        
        # Remove None values
        student_data = {k: v for k, v in student_data.items() if v is not None}
        parent_data = {k: v for k, v in parent_data.items() if v is not None}
        academic_data = {k: v for k, v in academic_data.items() if v is not None}
        
        return {
            "registration_number": sqlite_row["registration_number"],
            "student_data": student_data,
            "parent_data": parent_data,
            "academic_data": academic_data,
            "status": sqlite_row["status"],
            "created_at": sqlite_row["created_at"],
        }
    
    def _transform_document(self, sqlite_doc: dict) -> Dict[str, Any]:
        """Transform SQLite document to PostgreSQL format"""
        return {
            "document_type": sqlite_doc["field_name"],
            "filename": sqlite_doc["file_name"],
            "file_path": sqlite_doc["file_path"],
            "status": sqlite_doc["status"],
            "uploaded_at": sqlite_doc["uploaded_at"],
        }
    
    def _transform_tracking(self, sqlite_history: dict) -> Dict[str, Any]:
        """Transform SQLite status_history to PostgreSQL registration_tracking"""
        return {
            "status": sqlite_history["new_status"],
            "notes": sqlite_history.get("notes") or f"Changed from {sqlite_history['old_status']} by {sqlite_history['changed_by']}",
            "created_at": sqlite_history["changed_at"],
        }
    
    # =========================================================================
    # SYNC OPERATIONS
    # =========================================================================
    
    def sync_registration(self, registration_number: str) -> Tuple[bool, str]:
        """
        Sync single registration from SQLite to PostgreSQL
        
        Returns: (success, message)
        """
        try:
            # 1. Get data from SQLite
            with self.get_sqlite_conn() as sqlite_conn:
                cursor = sqlite_conn.cursor()
                
                # Get registration
                cursor.execute("""
                    SELECT * FROM registrations 
                    WHERE registration_number = ?
                """, (registration_number,))
                reg_row = cursor.fetchone()
                
                if not reg_row:
                    return False, f"Registration {registration_number} not found in SQLite"
                
                reg_data = dict(reg_row)
                
                # Get documents
                cursor.execute("""
                    SELECT * FROM documents 
                    WHERE registration_number = ?
                """, (registration_number,))
                doc_rows = [dict(row) for row in cursor.fetchall()]
                
                # Get status history
                cursor.execute("""
                    SELECT * FROM status_history 
                    WHERE registration_number = ?
                    ORDER BY changed_at
                """, (registration_number,))
                history_rows = [dict(row) for row in cursor.fetchall()]
            
            # 2. Transform data
            transformed = self._transform_registration(reg_data)
            
            # 3. Insert/Update to PostgreSQL
            with self.get_postgres_conn() as pg_conn:
                cursor = pg_conn.cursor(cursor_factory=RealDictCursor)
                
                # Upsert student_registrations
                cursor.execute("""
                    INSERT INTO student_registrations 
                        (registration_number, student_data, parent_data, academic_data, status, created_at, synced_at)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (registration_number) 
                    DO UPDATE SET
                        student_data = EXCLUDED.student_data,
                        parent_data = EXCLUDED.parent_data,
                        academic_data = EXCLUDED.academic_data,
                        status = EXCLUDED.status,
                        updated_at = CURRENT_TIMESTAMP,
                        synced_at = CURRENT_TIMESTAMP
                    RETURNING id
                """, (
                    transformed["registration_number"],
                    Json(transformed["student_data"]),
                    Json(transformed["parent_data"]),
                    Json(transformed["academic_data"]),
                    transformed["status"],
                    transformed["created_at"],
                ))
                
                registration_id = cursor.fetchone()["id"]
                
                # Sync documents
                for doc in doc_rows:
                    doc_data = self._transform_document(doc)
                    
                    # Check if exists
                    cursor.execute("""
                        SELECT id FROM registration_documents 
                        WHERE registration_id = %s AND document_type = %s
                    """, (registration_id, doc_data["document_type"]))
                    
                    existing = cursor.fetchone()
                    
                    if existing:
                        cursor.execute("""
                            UPDATE registration_documents SET
                                filename = %s, file_path = %s, status = %s
                            WHERE id = %s
                        """, (doc_data["filename"], doc_data["file_path"], 
                              doc_data["status"], existing["id"]))
                    else:
                        cursor.execute("""
                            INSERT INTO registration_documents 
                                (registration_id, document_type, filename, file_path, status, uploaded_at)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (registration_id, doc_data["document_type"], doc_data["filename"],
                              doc_data["file_path"], doc_data["status"], doc_data["uploaded_at"]))
                
                # Sync tracking history
                for hist in history_rows:
                    track_data = self._transform_tracking(hist)
                    
                    # Check if already synced (by timestamp)
                    cursor.execute("""
                        SELECT id FROM registration_tracking 
                        WHERE registration_id = %s AND created_at = %s
                    """, (registration_id, track_data["created_at"]))
                    
                    if not cursor.fetchone():
                        cursor.execute("""
                            INSERT INTO registration_tracking 
                                (registration_id, status, notes, created_at)
                            VALUES (%s, %s, %s, %s)
                        """, (registration_id, track_data["status"], 
                              track_data["notes"], track_data["created_at"]))
            
            self._log(f"✅ Synced registration: {registration_number}")
            return True, f"Successfully synced {registration_number}"
            
        except Exception as e:
            self._log(f"❌ Error syncing {registration_number}: {str(e)}")
            return False, str(e)
    
    def sync_conversation(self, session_id: str) -> Tuple[bool, str]:
        """
        Sync conversation from SQLite to PostgreSQL
        
        Returns: (success, message)
        """
        try:
            with self.get_sqlite_conn() as sqlite_conn:
                cursor = sqlite_conn.cursor()
                
                # Get conversation logs
                cursor.execute("""
                    SELECT * FROM conversation_logs 
                    WHERE session_id = ?
                    ORDER BY timestamp
                """, (session_id,))
                logs = [dict(row) for row in cursor.fetchall()]
                
                # Get registration data for conversation_state
                cursor.execute("""
                    SELECT current_step, raw_data, created_at, updated_at 
                    FROM registrations 
                    WHERE session_id = ?
                """, (session_id,))
                reg = cursor.fetchone()
            
            with self.get_postgres_conn() as pg_conn:
                cursor = pg_conn.cursor()
                
                # Pair user messages with bot responses
                i = 0
                while i < len(logs):
                    user_msg = None
                    bot_resp = None
                    timestamp = None
                    
                    if logs[i]["role"] == "user":
                        user_msg = logs[i]["message"]
                        timestamp = logs[i]["timestamp"]
                        if i + 1 < len(logs) and logs[i + 1]["role"] == "assistant":
                            bot_resp = logs[i + 1]["message"]
                            i += 2
                        else:
                            i += 1
                    elif logs[i]["role"] == "assistant":
                        bot_resp = logs[i]["message"]
                        timestamp = logs[i]["timestamp"]
                        i += 1
                    else:
                        i += 1
                        continue
                    
                    # Check if already exists
                    cursor.execute("""
                        SELECT id FROM conversations 
                        WHERE session_id = %s AND created_at = %s
                    """, (session_id, timestamp))
                    
                    if not cursor.fetchone():
                        cursor.execute("""
                            INSERT INTO conversations 
                                (session_id, user_message, bot_response, created_at)
                            VALUES (%s, %s, %s, %s)
                        """, (session_id, user_msg, bot_resp, timestamp))
                
                # Sync conversation_state
                if reg:
                    raw_data = json.loads(reg["raw_data"]) if reg["raw_data"] else {}
                    
                    cursor.execute("""
                        INSERT INTO conversation_state 
                            (session_id, current_step, collected_data, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (session_id) 
                        DO UPDATE SET
                            current_step = EXCLUDED.current_step,
                            collected_data = EXCLUDED.collected_data,
                            updated_at = EXCLUDED.updated_at
                    """, (session_id, reg["current_step"], Json(raw_data),
                          reg["created_at"], reg["updated_at"]))
            
            self._log(f"✅ Synced conversation: {session_id}")
            return True, f"Successfully synced conversation {session_id}"
            
        except Exception as e:
            self._log(f"❌ Error syncing conversation {session_id}: {str(e)}")
            return False, str(e)
    
    def sync_all_pending(self) -> Dict[str, Any]:
        """
        Sync all confirmed registrations that haven't been synced yet
        
        Returns: sync report
        """
        report = {
            "started_at": datetime.now().isoformat(),
            "registrations_synced": 0,
            "conversations_synced": 0,
            "errors": []
        }
        
        try:
            # Get all confirmed registrations from SQLite
            with self.get_sqlite_conn() as sqlite_conn:
                cursor = sqlite_conn.cursor()
                
                # Get registrations with registration_number (confirmed)
                cursor.execute("""
                    SELECT registration_number, session_id FROM registrations 
                    WHERE registration_number IS NOT NULL
                    AND status != 'draft'
                """)
                registrations = cursor.fetchall()
            
            # Sync each registration
            for reg in registrations:
                reg_num = reg["registration_number"]
                session_id = reg["session_id"]
                
                # Sync registration
                success, msg = self.sync_registration(reg_num)
                if success:
                    report["registrations_synced"] += 1
                else:
                    report["errors"].append({"type": "registration", "id": reg_num, "error": msg})
                
                # Sync conversation
                success, msg = self.sync_conversation(session_id)
                if success:
                    report["conversations_synced"] += 1
                else:
                    report["errors"].append({"type": "conversation", "id": session_id, "error": msg})
            
            report["completed_at"] = datetime.now().isoformat()
            report["success"] = len(report["errors"]) == 0
            
        except Exception as e:
            report["errors"].append({"type": "general", "error": str(e)})
            report["success"] = False
        
        self._log(f"📊 Sync completed: {report['registrations_synced']} registrations, {report['conversations_synced']} conversations")
        return report
    
    def sync_single_by_session(self, session_id: str) -> Dict[str, Any]:
        """Sync single session (registration + conversation)"""
        report = {
            "session_id": session_id,
            "registration_synced": False,
            "conversation_synced": False,
            "errors": []
        }
        
        try:
            # Get registration number
            with self.get_sqlite_conn() as sqlite_conn:
                cursor = sqlite_conn.cursor()
                cursor.execute("""
                    SELECT registration_number FROM registrations 
                    WHERE session_id = ?
                """, (session_id,))
                row = cursor.fetchone()
            
            if row and row["registration_number"]:
                success, msg = self.sync_registration(row["registration_number"])
                report["registration_synced"] = success
                if not success:
                    report["errors"].append(msg)
            
            success, msg = self.sync_conversation(session_id)
            report["conversation_synced"] = success
            if not success:
                report["errors"].append(msg)
            
        except Exception as e:
            report["errors"].append(str(e))
        
        report["success"] = report["registration_synced"] or report["conversation_synced"]
        return report
    
    # =========================================================================
    # UTILITY
    # =========================================================================
    
    def _log(self, message: str):
        """Log sync activity"""
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] {message}"
        self.sync_log.append(log_entry)
        print(log_entry)
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get sync status overview"""
        status = {
            "sqlite": {"registrations": 0, "confirmed": 0, "documents": 0},
            "postgres": {"registrations": 0, "documents": 0},
            "pending_sync": 0
        }
        
        try:
            with self.get_sqlite_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM registrations")
                status["sqlite"]["registrations"] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM registrations WHERE registration_number IS NOT NULL")
                status["sqlite"]["confirmed"] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM documents")
                status["sqlite"]["documents"] = cursor.fetchone()[0]
        except:
            pass
        
        try:
            with self.get_postgres_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM student_registrations")
                status["postgres"]["registrations"] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM registration_documents")
                status["postgres"]["documents"] = cursor.fetchone()[0]
        except:
            pass
        
        status["pending_sync"] = status["sqlite"]["confirmed"] - status["postgres"]["registrations"]
        
        return status


# =========================================================================
# SINGLETON & HELPER FUNCTIONS
# =========================================================================

_sync_service: Optional[SyncService] = None

def get_sync_service() -> SyncService:
    global _sync_service
    if _sync_service is None:
        _sync_service = SyncService()
    return _sync_service


def run_sync():
    """Run full sync - can be called from scheduler"""
    service = get_sync_service()
    service.init_postgres_tables()
    return service.sync_all_pending()


def sync_registration(registration_number: str):
    """Sync single registration - can be called after confirmation"""
    service = get_sync_service()
    return service.sync_registration(registration_number)


# =========================================================================
# CLI INTERFACE
# =========================================================================

if __name__ == "__main__":
    import sys
    
    service = SyncService()
    
    if len(sys.argv) < 2:
        print("""
Usage:
    python sync_service.py init          - Initialize PostgreSQL tables
    python sync_service.py status        - Show sync status
    python sync_service.py sync-all      - Sync all pending registrations
    python sync_service.py sync <reg_no> - Sync specific registration
        """)
        sys.exit(0)
    
    command = sys.argv[1]
    
    if command == "init":
        service.init_postgres_tables()
        print("✅ PostgreSQL tables initialized")
        
    elif command == "status":
        status = service.get_sync_status()
        print("\n📊 SYNC STATUS")
        print("=" * 40)
        print(f"SQLite Registrations: {status['sqlite']['registrations']}")
        print(f"SQLite Confirmed: {status['sqlite']['confirmed']}")
        print(f"SQLite Documents: {status['sqlite']['documents']}")
        print("-" * 40)
        print(f"PostgreSQL Registrations: {status['postgres']['registrations']}")
        print(f"PostgreSQL Documents: {status['postgres']['documents']}")
        print("-" * 40)
        print(f"Pending Sync: {status['pending_sync']}")
        
    elif command == "sync-all":
        service.init_postgres_tables()
        report = service.sync_all_pending()
        print("\n📊 SYNC REPORT")
        print("=" * 40)
        print(f"Registrations Synced: {report['registrations_synced']}")
        print(f"Conversations Synced: {report['conversations_synced']}")
        print(f"Errors: {len(report['errors'])}")
        if report['errors']:
            for err in report['errors']:
                print(f"  - {err}")
        
    elif command == "sync" and len(sys.argv) > 2:
        reg_number = sys.argv[2]
        service.init_postgres_tables()
        success, msg = service.sync_registration(reg_number)
        print(f"\n{'✅' if success else '❌'} {msg}")
        
    else:
        print(f"Unknown command: {command}")