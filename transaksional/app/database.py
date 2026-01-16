"""
Database Manager - Complete PostgreSQL Version
===============================================
Full PostgreSQL database for:
- Registrations & Documents
- Auto-triggers
- Ratings
- Session Activity
- Form Config
- Upload Batches
"""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from contextlib import contextmanager
import os

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool


class DatabaseManager:
    """
    PostgreSQL Database Manager with connection pooling.
    """
    
    def __init__(self, database_url: str = None):
        self.database_url = database_url or os.getenv(
            "DATABASE_URL", 
            "postgresql://postgres:postgres@localhost:5432/ypi_alazhar"
        )
        
        # Connection pool with keepalive
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=self.database_url,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5
        )
        
        self._init_db()
        self._run_migrations()
    
    @contextmanager
    def get_connection(self):
        """Get connection from pool with auto-commit/rollback and retry logic"""
        conn = None
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                conn = self._pool.getconn()
                
                # Test connection is alive
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.close()
                except Exception:
                    try:
                        self._pool.putconn(conn, close=True)
                    except:
                        pass
                    conn = self._pool.getconn()
                
                yield conn
                conn.commit()
                break
                
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                retry_count += 1
                print(f"⚠️ Database connection error (attempt {retry_count}/{max_retries}): {e}")
                
                if conn:
                    try:
                        conn.rollback()
                    except:
                        pass
                    try:
                        self._pool.putconn(conn, close=True)
                    except:
                        pass
                    conn = None
                
                if retry_count >= max_retries:
                    print("❌ Max retries reached, recreating connection pool...")
                    self._recreate_pool()
                    raise
                    
                import time
                time.sleep(0.5 * retry_count)
                
            except Exception as e:
                if conn:
                    try:
                        conn.rollback()
                    except:
                        pass
                raise
            finally:
                if conn:
                    try:
                        self._pool.putconn(conn)
                    except:
                        pass
    
    def _recreate_pool(self):
        """Recreate connection pool if all connections are dead"""
        try:
            if self._pool:
                self._pool.closeall()
        except:
            pass
        
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=self.database_url,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5
        )
        print("✅ Connection pool recreated")
    
    def _init_db(self):
        """Initialize all database tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # =========================================================
            # CORE TABLES
            # =========================================================
            
            # Registrations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS registrations (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT UNIQUE NOT NULL,
                    user_id TEXT,
                    registration_number TEXT UNIQUE,
                    status TEXT DEFAULT 'draft',
                    current_step TEXT,
                    completion_percentage REAL DEFAULT 0,
                    raw_data JSONB,
                    student_data JSONB,
                    documents JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    confirmed_at TIMESTAMP,
                    expires_at TIMESTAMP,
                    last_activity_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    idle_trigger_count INTEGER DEFAULT 0,
                    last_trigger_at TIMESTAMP
                )
            """)
            
            # registration_documents table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS registration_documents (
                    id SERIAL PRIMARY KEY,
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
                    upload_batch_id TEXT,
                    file_order INTEGER DEFAULT 0,
                    FOREIGN KEY (session_id) REFERENCES registrations(session_id) ON DELETE CASCADE
                )
            """)
            
            # Conversation logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_logs (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    message TEXT,
                    metadata JSONB,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES registrations(session_id) ON DELETE CASCADE
                )
            """)
            
            # Status history
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS status_history (
                    id SERIAL PRIMARY KEY,
                    registration_number TEXT NOT NULL,
                    old_status TEXT,
                    new_status TEXT NOT NULL,
                    changed_by TEXT DEFAULT 'system',
                    notes TEXT,
                    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Migrations tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS migrations (
                    id SERIAL PRIMARY KEY,
                    migration_name TEXT UNIQUE NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # =========================================================
            # EXTENSION TABLES
            # =========================================================
            
            # Upload batches table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS upload_batches (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    field_name TEXT,
                    total_files INTEGER DEFAULT 0,
                    uploaded_files INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)
            
            # Auto triggers table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auto_triggers (
                    id SERIAL PRIMARY KEY,
                    trigger_name TEXT UNIQUE NOT NULL,
                    trigger_type TEXT NOT NULL,
                    conditions JSONB NOT NULL,
                    message_template TEXT NOT NULL,
                    priority INTEGER DEFAULT 0,
                    max_triggers_per_session INTEGER DEFAULT 3,
                    cooldown_minutes INTEGER DEFAULT 10,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Trigger logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trigger_logs (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    trigger_id INTEGER REFERENCES auto_triggers(id),
                    trigger_name TEXT,
                    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message_sent TEXT,
                    user_responded BOOLEAN DEFAULT FALSE,
                    response_at TIMESTAMP
                )
            """)
            
            # Session activity table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_activity (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT UNIQUE NOT NULL,
                    user_id TEXT,
                    last_activity_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_message_at TIMESTAMP,
                    current_step TEXT,
                    completion_percentage REAL DEFAULT 0,
                    is_idle BOOLEAN DEFAULT FALSE,
                    idle_since TIMESTAMP,
                    total_idle_triggers INTEGER DEFAULT 0
                )
            """)
            
            # Ratings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ratings (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_id TEXT,
                    registration_number TEXT,
                    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
                    feedback_text TEXT,
                    rating_category TEXT DEFAULT 'overall',
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Rating prompts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rating_prompts (
                    id SERIAL PRIMARY KEY,
                    prompt_type TEXT NOT NULL,
                    conditions JSONB,
                    prompt_message TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Rating prompt logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rating_prompt_logs (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    prompt_id INTEGER REFERENCES rating_prompts(id),
                    shown_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Form configs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS form_configs (
                    id SERIAL PRIMARY KEY,
                    config_key TEXT UNIQUE NOT NULL,
                    config_type TEXT DEFAULT 'yaml',
                    config_data JSONB NOT NULL,
                    version TEXT DEFAULT '1.0.0',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Form steps table (for database config)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS form_steps (
                    id SERIAL PRIMARY KEY,
                    config_id INTEGER REFERENCES form_configs(id) ON DELETE CASCADE,
                    step_id TEXT NOT NULL,
                    step_name TEXT NOT NULL,
                    description TEXT,
                    step_order INTEGER DEFAULT 0,
                    is_mandatory BOOLEAN DEFAULT TRUE,
                    can_skip BOOLEAN DEFAULT FALSE,
                    skip_conditions JSONB,
                    icon TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Form fields table (for database config)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS form_fields (
                    id SERIAL PRIMARY KEY,
                    config_id INTEGER REFERENCES form_configs(id) ON DELETE CASCADE,
                    field_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    field_label TEXT NOT NULL,
                    field_type TEXT DEFAULT 'text',
                    is_mandatory BOOLEAN DEFAULT FALSE,
                    validation JSONB,
                    options JSONB,
                    examples JSONB,
                    tips TEXT,
                    extract_keywords JSONB,
                    auto_formats JSONB,
                    auto_clean BOOLEAN DEFAULT FALSE,
                    default_value TEXT,
                    field_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Form messages table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS form_messages (
                    id SERIAL PRIMARY KEY,
                    config_id INTEGER REFERENCES form_configs(id) ON DELETE CASCADE,
                    message_key TEXT NOT NULL,
                    message_template TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE
                )
            """)
            
            # Form commands table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS form_commands (
                    id SERIAL PRIMARY KEY,
                    config_id INTEGER REFERENCES form_configs(id) ON DELETE CASCADE,
                    command_name TEXT NOT NULL,
                    keywords JSONB,
                    pattern TEXT,
                    is_active BOOLEAN DEFAULT TRUE
                )
            """)
            
            # System settings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_settings (
                    id SERIAL PRIMARY KEY,
                    setting_key TEXT UNIQUE NOT NULL,
                    setting_value JSONB NOT NULL,
                    description TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # =========================================================
            # INDEXES
            # =========================================================
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_reg_session ON registrations(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_reg_number ON registrations(registration_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_reg_status ON registrations(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_reg_user_id ON registrations(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_doc_session ON registration_documents(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_doc_batch ON registration_documents(upload_batch_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_doc_field ON registration_documents(field_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_upload_batch_session ON upload_batches(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trigger_log_session ON trigger_logs(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_activity_idle ON session_activity(is_idle)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_activity_last ON session_activity(last_activity_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_rating_session ON ratings(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_rating_created ON ratings(created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_form_steps_config ON form_steps(config_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_form_fields_config ON form_fields(config_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_form_fields_step ON form_fields(step_id)")
            
            # =========================================================
            # INSERT DEFAULT DATA
            # =========================================================
            
            # Check and insert default triggers
            cursor.execute("SELECT COUNT(*) as cnt FROM auto_triggers")
            if cursor.fetchone()['cnt'] == 0:
                self._insert_default_triggers(cursor)
            
            # Check and insert default rating prompts
            cursor.execute("SELECT COUNT(*) as cnt FROM rating_prompts")
            if cursor.fetchone()['cnt'] == 0:
                self._insert_default_rating_prompts(cursor)
            
            print("✅ PostgreSQL database initialized")
    
    def _insert_default_triggers(self, cursor):
        """Insert default auto triggers"""
        default_triggers = [
            ("idle_reminder", "idle", {"idle_minutes": 5},
             "Hai! Sepertinya kamu sedang sibuk. Jangan lupa lanjutkan pendaftaran ya! 😊\n\nKamu sudah mengisi {completion}% data.",
             10, 2, 10),
            ("document_stuck", "step_stuck", {"step": "documents", "stuck_minutes": 10},
             "Butuh bantuan upload dokumen? 📄\n\nKamu bisa upload beberapa file sekaligus lho!",
             8, 1, 15),
            ("incomplete_reminder", "incomplete", {"completion_below": 50, "idle_minutes": 15},
             "Data pendaftaran kamu baru {completion}% lengkap.\n\nYuk selesaikan! Ketik 'lanjut' untuk melanjutkan. 💪",
             5, 1, 30),
            ("rating_after_complete", "rating_prompt", {"after_completion": True},
             "Terima kasih telah menyelesaikan pendaftaran! 🎉\n\nBoleh minta rating? Ketik angka 1-5 ⭐",
             15, 1, 60)
        ]
        
        for trigger in default_triggers:
            cursor.execute("""
                INSERT INTO auto_triggers 
                (trigger_name, trigger_type, conditions, message_template, priority, max_triggers_per_session, cooldown_minutes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (trigger_name) DO NOTHING
            """, (trigger[0], trigger[1], json.dumps(trigger[2]), trigger[3], trigger[4], trigger[5], trigger[6]))
        
        print("   ✅ Default triggers inserted")
    
    def _insert_default_rating_prompts(self, cursor):
        """Insert default rating prompts"""
        default_prompts = [
            ("post_registration", {"after_completion": True},
             "🌟 Bagaimana pengalaman kamu?\n\nKetik angka 1-5:\n⭐1 Buruk | ⭐⭐2 Kurang | ⭐⭐⭐3 Cukup | ⭐⭐⭐⭐4 Bagus | ⭐⭐⭐⭐⭐5 Sangat Bagus"),
            ("idle_exit", {"idle_minutes": 30},
             "Sebelum pergi, boleh berikan rating? Ketik 1-5 ⭐")
        ]
        
        for prompt in default_prompts:
            cursor.execute("""
                INSERT INTO rating_prompts (prompt_type, conditions, prompt_message)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (prompt[0], json.dumps(prompt[1]), prompt[2]))
        
        print("   ✅ Default rating prompts inserted")
    
    def _run_migrations(self):
        """Run pending migrations"""
        migrations = [
            ("001_initial", lambda c: None),
            ("002_add_batch_columns", self._migrate_add_batch_columns),
            ("003_add_activity_columns", self._migrate_add_activity_columns),
        ]
        
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            for migration_name, migration_func in migrations:
                cursor.execute(
                    "SELECT id FROM migrations WHERE migration_name = %s", 
                    (migration_name,)
                )
                if cursor.fetchone() is None:
                    migration_func(cursor)
                    cursor.execute(
                        "INSERT INTO migrations (migration_name) VALUES (%s)",
                        (migration_name,)
                    )
                    print(f"   ✅ Migration applied: {migration_name}")
    
    def _migrate_add_batch_columns(self, cursor):
        """Migration: Add batch columns to registration_documents"""
        try:
            cursor.execute("""
                ALTER TABLE registration_documents 
                ADD COLUMN IF NOT EXISTS upload_batch_id TEXT,
                ADD COLUMN IF NOT EXISTS file_order INTEGER DEFAULT 0
            """)
        except:
            pass
    
    def _migrate_add_activity_columns(self, cursor):
        """Migration: Add activity columns to registrations"""
        try:
            cursor.execute("""
                ALTER TABLE registrations 
                ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ADD COLUMN IF NOT EXISTS idle_trigger_count INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS last_trigger_at TIMESTAMP
            """)
        except:
            pass
    
    # =========================================================================
    # DRAFT MANAGEMENT
    # =========================================================================
    
    def save_draft(self, session_id: str, current_step: str, raw_data: Dict, 
                   completion_percentage: float, user_id: str = None) -> bool:
        """Save or update draft registration"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            expires_at = datetime.now() + timedelta(days=7)
            
            cursor.execute("""
                INSERT INTO registrations 
                (session_id, user_id, status, current_step, completion_percentage, raw_data, expires_at, last_activity_at)
                VALUES (%s, %s, 'draft', %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (session_id) DO UPDATE SET
                    current_step = EXCLUDED.current_step,
                    completion_percentage = EXCLUDED.completion_percentage,
                    raw_data = EXCLUDED.raw_data,
                    user_id = COALESCE(EXCLUDED.user_id, registrations.user_id),
                    updated_at = CURRENT_TIMESTAMP,
                    last_activity_at = CURRENT_TIMESTAMP,
                    expires_at = EXCLUDED.expires_at
            """, (session_id, user_id, current_step, completion_percentage, 
                  json.dumps(raw_data), expires_at))
            
            return True
    
    def get_draft(self, session_id: str) -> Optional[Dict]:
        """Get draft by session_id"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT * FROM registrations 
                WHERE session_id = %s AND status = 'draft'
                AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            """, (session_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    "session_id": row["session_id"],
                    "user_id": row["user_id"],
                    "current_step": row["current_step"],
                    "completion_percentage": row["completion_percentage"],
                    "raw_data": row["raw_data"] or {},
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                }
            return None
    
    def get_drafts_by_user(self, user_id: str) -> List[Dict]:
        """Get all drafts for a user"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT * FROM registrations 
                WHERE user_id = %s AND status = 'draft'
                AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                ORDER BY updated_at DESC
            """, (user_id,))
            rows = cursor.fetchall()
            
            return [{
                "session_id": row["session_id"],
                "user_id": row["user_id"],
                "current_step": row["current_step"],
                "completion_percentage": row["completion_percentage"],
                "raw_data": row["raw_data"] or {},
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            } for row in rows]
    
    # =========================================================================
    # REGISTRATION MANAGEMENT
    # =========================================================================
    
    def save_registration(self, session, registration_number: str, user_id: str = None) -> bool:
        """Convert draft to confirmed registration"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            student_data = {
                "nama_lengkap": session.get_field("nama_lengkap"),
                "nama_sekolah": session.get_field("nama_sekolah"),
                "tingkatan": session.get_field("tingkatan"),
                "program": session.get_field("program"),
                "tempat_lahir": session.get_field("tempat_lahir"),
                "tanggal_lahir": session.get_field("tanggal_lahir"),
                "jenis_kelamin": session.get_field("jenis_kelamin"),
            }
            
            cursor.execute("SELECT user_id FROM registrations WHERE session_id = %s", 
                          (session.session_id,))
            existing = cursor.fetchone()
            final_user_id = user_id or (existing["user_id"] if existing else None)
            
            cursor.execute("""
                INSERT INTO registrations 
                (session_id, user_id, registration_number, status, current_step, 
                 completion_percentage, raw_data, student_data, confirmed_at)
                VALUES (%s, %s, %s, 'pending_payment', %s, 100, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (session_id) DO UPDATE SET
                    registration_number = EXCLUDED.registration_number,
                    user_id = COALESCE(EXCLUDED.user_id, registrations.user_id),
                    status = 'pending_payment',
                    raw_data = EXCLUDED.raw_data,
                    student_data = EXCLUDED.student_data,
                    confirmed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
            """, (session.session_id, final_user_id, registration_number, session.current_step,
                  json.dumps(session.raw_data), json.dumps(student_data)))
            
            cursor.execute("""
                UPDATE registration_documents SET registration_number = %s
                WHERE session_id = %s
            """, (registration_number, session.session_id))
            
            self._log_status_change_internal(cursor, registration_number, None, 'pending_payment', 
                                            'system', 'Pendaftaran dikonfirmasi')
            
            return True
    
    def get_registration(self, registration_number: str) -> Optional[Dict]:
        """Get registration by registration number"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT * FROM registrations WHERE registration_number = %s
            """, (registration_number,))
            row = cursor.fetchone()
            
            if row:
                cursor.execute("""
                    SELECT * FROM registration_documents WHERE registration_number = %s
                    ORDER BY uploaded_at
                """, (registration_number,))
                docs = cursor.fetchall()
                
                cursor.execute("""
                    SELECT * FROM status_history WHERE registration_number = %s
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
                    "raw_data": row["raw_data"] or {},
                    "student_data": row["student_data"] or {},
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
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM registrations WHERE session_id = %s", (session_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    "registration_number": row["registration_number"],
                    "session_id": row["session_id"],
                    "user_id": row["user_id"],
                    "status": row["status"],
                    "current_step": row["current_step"],
                    "completion_percentage": row["completion_percentage"],
                    "raw_data": row["raw_data"] or {},
                    "student_data": row["student_data"] or {},
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                }
            return None
    
    def get_registrations_by_user(self, user_id: str, status: str = None) -> List[Dict]:
        """Get all registrations for a user"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            if status:
                cursor.execute("""
                    SELECT * FROM registrations 
                    WHERE user_id = %s AND status = %s
                    ORDER BY updated_at DESC
                """, (user_id, status))
            else:
                cursor.execute("""
                    SELECT * FROM registrations 
                    WHERE user_id = %s
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
                "raw_data": row["raw_data"] or {},
                "student_data": row["student_data"] or {},
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "confirmed_at": row["confirmed_at"]
            } for row in rows]
    
    def update_registration_status(self, registration_number: str, status: str, 
                                   notes: str = None, changed_by: str = "system") -> bool:
        """Update registration status with history"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("SELECT status FROM registrations WHERE registration_number = %s",
                          (registration_number,))
            row = cursor.fetchone()
            if not row:
                return False
            
            old_status = row["status"]
            
            cursor.execute("""
                UPDATE registrations SET status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE registration_number = %s
            """, (status, registration_number))
            
            self._log_status_change_internal(cursor, registration_number, old_status, status, 
                                            changed_by, notes)
            
            return True
    
    def update_registration_user(self, session_id: str, user_id: str) -> bool:
        """Update user_id for a registration"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE registrations SET user_id = %s, updated_at = CURRENT_TIMESTAMP
                WHERE session_id = %s
            """, (user_id, session_id))
            return cursor.rowcount > 0
    
    def _log_status_change_internal(self, cursor, registration_number: str, old_status: str,
                                    new_status: str, changed_by: str, notes: str):
        """Log status change to history"""
        cursor.execute("""
            INSERT INTO status_history 
            (registration_number, old_status, new_status, changed_by, notes)
            VALUES (%s, %s, %s, %s, %s)
        """, (registration_number, old_status, new_status, changed_by, notes))
    
    def _log_status_change(self, registration_number: str, old_status: str,
                          new_status: str, changed_by: str, notes: str):
        """Log status change to history"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            self._log_status_change_internal(cursor, registration_number, old_status, 
                                            new_status, changed_by, notes)
    
    # =========================================================================
    # DOCUMENT MANAGEMENT - FIXED WITH batch_id SUPPORT
    # =========================================================================
    
    def save_document(self, session_id: str, field_name: str, file_name: str,
                     file_path: str, file_size: int, file_type: str,
                     registration_number: str = None, batch_id: str = None, 
                     file_order: int = 0) -> int:
        """Save uploaded document with batch support"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # For multiple files with same field_name, append order
            if batch_id:
                # Multiple upload - always insert new
                cursor.execute("""
                    INSERT INTO registration_documents 
                    (session_id, registration_number, field_name, file_name, 
                     file_path, file_size, file_type, upload_batch_id, file_order)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (session_id, registration_number, field_name, file_name,
                      file_path, file_size, file_type, batch_id, file_order))
                return cursor.fetchone()["id"]
            else:
                # Single upload - check if exists
                cursor.execute("""
                    SELECT id FROM registration_documents 
                    WHERE session_id = %s AND field_name = %s AND upload_batch_id IS NULL
                """, (session_id, field_name))
                exists = cursor.fetchone()
                
                if exists:
                    cursor.execute("""
                        UPDATE registration_documents SET
                            file_name = %s, file_path = %s, file_size = %s,
                            file_type = %s, uploaded_at = CURRENT_TIMESTAMP, status = 'uploaded'
                        WHERE session_id = %s AND field_name = %s AND upload_batch_id IS NULL
                        RETURNING id
                    """, (file_name, file_path, file_size, file_type, session_id, field_name))
                    return cursor.fetchone()["id"]
                else:
                    cursor.execute("""
                        INSERT INTO registration_documents 
                        (session_id, registration_number, field_name, file_name, 
                         file_path, file_size, file_type, file_order)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (session_id, registration_number, field_name, file_name,
                          file_path, file_size, file_type, file_order))
                    return cursor.fetchone()["id"]
    
    def get_documents(self, session_id: str = None, registration_number: str = None) -> List[Dict]:
        """Get documents by session or registration number"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            if registration_number:
                cursor.execute("""
                    SELECT * FROM registration_documents WHERE registration_number = %s
                    ORDER BY field_name, file_order
                """, (registration_number,))
            elif session_id:
                cursor.execute("""
                    SELECT * FROM registration_documents WHERE session_id = %s
                    ORDER BY field_name, file_order
                """, (session_id,))
            else:
                return []
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_documents_by_field(self, session_id: str, field_name: str) -> List[Dict]:
        """Get all documents for a specific field"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT * FROM registration_documents 
                WHERE session_id = %s AND field_name = %s
                ORDER BY file_order
            """, (session_id, field_name))
            return [dict(row) for row in cursor.fetchall()]
    
    def count_documents_by_field(self, session_id: str, field_name: str) -> int:
        """Count documents for a specific field"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM registration_documents 
                WHERE session_id = %s AND field_name = %s
            """, (session_id, field_name))
            return cursor.fetchone()["cnt"]
    
    def update_document_status(self, doc_id: int, status: str, notes: str = None) -> bool:
        """Update document verification status"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE registration_documents SET 
                    status = %s, notes = %s,
                    verified_at = CASE WHEN %s = 'verified' THEN CURRENT_TIMESTAMP ELSE verified_at END
                WHERE id = %s
            """, (status, notes, status, doc_id))
            return cursor.rowcount > 0
    
    # =========================================================================
    # UPLOAD BATCH MANAGEMENT
    # =========================================================================
    
    def create_upload_batch(self, batch_id: str, session_id: str, 
                            field_name: str, total_files: int) -> bool:
        """Create a new upload batch"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO upload_batches (id, session_id, field_name, total_files, status)
                VALUES (%s, %s, %s, %s, 'pending')
            """, (batch_id, session_id, field_name, total_files))
            return True
    
    def update_upload_batch(self, batch_id: str, uploaded_files: int, status: str) -> bool:
        """Update upload batch status"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            completed_at = datetime.now() if status in ['completed', 'failed', 'partial'] else None
            cursor.execute("""
                UPDATE upload_batches 
                SET uploaded_files = %s, status = %s, completed_at = %s
                WHERE id = %s
            """, (uploaded_files, status, completed_at, batch_id))
            return cursor.rowcount > 0
    
    def get_upload_batch(self, batch_id: str) -> Optional[Dict]:
        """Get upload batch info"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM upload_batches WHERE id = %s", (batch_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def get_documents_by_batch(self, batch_id: str) -> List[Dict]:
        """Get all documents in a batch"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT * FROM registration_documents WHERE upload_batch_id = %s
                ORDER BY file_order
            """, (batch_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def delete_upload_batch(self, batch_id: str) -> bool:
        """Delete upload batch and its documents"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM registration_documents WHERE upload_batch_id = %s", (batch_id,))
            cursor.execute("DELETE FROM upload_batches WHERE id = %s", (batch_id,))
            return cursor.rowcount > 0
    
    # =========================================================================
    # TRIGGER MANAGEMENT FOR CONFIG LOADER
    # =========================================================================
    
    def get_active_sessions_for_trigger(self) -> List[Dict]:
        """Get sessions yang aktif untuk di-trigger"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT 
                    session_id,
                    user_id,
                    current_step,
                    completion_percentage,
                    last_activity_at,
                    idle_trigger_count,
                    EXTRACT(EPOCH FROM (NOW() - last_activity_at))/60 as idle_minutes
                FROM registrations 
                WHERE status = 'draft'
                AND last_activity_at > NOW() - INTERVAL '24 hours'
                AND last_activity_at < NOW() - INTERVAL '3 minutes'
                ORDER BY last_activity_at DESC
                LIMIT 100
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def record_trigger_sent(self, session_id: str, trigger_id: str, 
                            trigger_type: str, message: str):
        """Record bahwa trigger sudah dikirim"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Update trigger count di registrations
            cursor.execute("""
                UPDATE registrations 
                SET idle_trigger_count = COALESCE(idle_trigger_count, 0) + 1,
                    last_trigger_at = NOW()
                WHERE session_id = %s
            """, (session_id,))
            
            # Insert ke trigger_logs
            cursor.execute("""
                INSERT INTO trigger_logs 
                (session_id, trigger_name, message_sent)
                VALUES (%s, %s, %s)
            """, (session_id, trigger_id, message))
    
    # =========================================================================
    # AUTO-TRIGGER MANAGEMENT
    # =========================================================================
    
    def get_active_triggers(self) -> List[Dict]:
        """Get all active auto-triggers"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT id, trigger_name, trigger_type, conditions, message_template,
                       priority, max_triggers_per_session, cooldown_minutes, is_active
                FROM auto_triggers
                WHERE is_active = TRUE
                ORDER BY priority DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def log_trigger(self, session_id: str, trigger_id: int, 
                    trigger_name: str, message_sent: str) -> int:
        """Log a triggered message"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                INSERT INTO trigger_logs (session_id, trigger_id, trigger_name, message_sent)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (session_id, trigger_id, trigger_name, message_sent))
            return cursor.fetchone()["id"]
    
    def mark_trigger_responded(self, session_id: str, trigger_id: int) -> bool:
        """Mark that user responded to a trigger"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE trigger_logs 
                SET user_responded = TRUE, response_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id FROM trigger_logs 
                    WHERE session_id = %s AND trigger_id = %s AND user_responded = FALSE
                    ORDER BY triggered_at DESC LIMIT 1
                )
            """, (session_id, trigger_id))
            return cursor.rowcount > 0
    
    def update_session_activity(self, session_id: str, user_id: str = None,
                                 current_step: str = None, 
                                 completion: float = None) -> bool:
        """Update session activity for idle detection"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO session_activity 
                (session_id, user_id, last_activity_at, last_message_at, 
                 current_step, completion_percentage, is_idle, idle_since)
                VALUES (%s, %s, NOW(), NOW(), %s, COALESCE(%s, 0), FALSE, NULL)
                ON CONFLICT (session_id) DO UPDATE SET
                    user_id = COALESCE(%s, session_activity.user_id),
                    last_activity_at = NOW(),
                    last_message_at = NOW(),
                    current_step = COALESCE(%s, session_activity.current_step),
                    completion_percentage = COALESCE(%s, session_activity.completion_percentage),
                    is_idle = FALSE,
                    idle_since = NULL
            """, (session_id, user_id, current_step, completion,
                  user_id, current_step, completion))
            return True
    
    def get_idle_sessions(self, idle_minutes: int = 5) -> List[Dict]:
        """Get all idle sessions"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT session_id, user_id, current_step, completion_percentage,
                       last_activity_at, idle_since, 
                       EXTRACT(EPOCH FROM (NOW() - last_activity_at))/60 as idle_minutes,
                       total_idle_triggers
                FROM session_activity
                WHERE last_activity_at < NOW() - INTERVAL '%s minutes'
                ORDER BY last_activity_at ASC
            """, (idle_minutes,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_session_activity(self, session_id: str) -> Optional[Dict]:
        """Get session activity info"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT session_id, user_id, current_step, completion_percentage,
                       last_activity_at, idle_since, is_idle, total_idle_triggers,
                       EXTRACT(EPOCH FROM (NOW() - last_activity_at))/60 as idle_minutes
                FROM session_activity
                WHERE session_id = %s
            """, (session_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    # =========================================================================
    # RATING MANAGEMENT
    # =========================================================================
    
    def save_rating(self, session_id: str, rating: int, 
                    user_id: str = None, registration_number: str = None,
                    feedback_text: str = None, category: str = "overall",
                    metadata: Dict = None) -> int:
        """Save a user rating"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                INSERT INTO ratings 
                (session_id, user_id, registration_number, rating, 
                 feedback_text, rating_category, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (session_id, user_id, registration_number, rating,
                  feedback_text, category, json.dumps(metadata or {})))
            return cursor.fetchone()["id"]
    
    def get_ratings(self, session_id: str = None, user_id: str = None,
                    limit: int = 100) -> List[Dict]:
        """Get ratings with optional filters"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            where_clauses = []
            params = []
            
            if session_id:
                where_clauses.append("session_id = %s")
                params.append(session_id)
            if user_id:
                where_clauses.append("user_id = %s")
                params.append(user_id)
            
            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
            params.append(limit)
            
            cursor.execute(f"""
                SELECT id, session_id, user_id, registration_number, rating,
                       feedback_text, rating_category, metadata, created_at
                FROM ratings
                {where_sql}
                ORDER BY created_at DESC
                LIMIT %s
            """, params)
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_rating_stats(self, start_date: datetime = None,
                          end_date: datetime = None) -> Dict[str, Any]:
        """Get rating statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            where_clauses = []
            params = []
            
            if start_date:
                where_clauses.append("created_at >= %s")
                params.append(start_date)
            if end_date:
                where_clauses.append("created_at <= %s")
                params.append(end_date)
            
            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
            
            cursor.execute(f"""
                SELECT 
                    COUNT(*) as total_ratings,
                    COALESCE(AVG(rating)::NUMERIC(3,2), 0) as avg_rating,
                    COUNT(*) FILTER (WHERE rating >= 4) as positive_ratings,
                    COUNT(*) FILTER (WHERE rating <= 2) as negative_ratings,
                    COUNT(*) FILTER (WHERE rating = 5) as five_star,
                    COUNT(*) FILTER (WHERE rating = 4) as four_star,
                    COUNT(*) FILTER (WHERE rating = 3) as three_star,
                    COUNT(*) FILTER (WHERE rating = 2) as two_star,
                    COUNT(*) FILTER (WHERE rating = 1) as one_star
                FROM ratings
                {where_sql}
            """, params if params else None)
            
            row = cursor.fetchone()
            return dict(row) if row else {}
    
    def get_rating_prompts(self) -> List[Dict]:
        """Get active rating prompts"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT id, prompt_type, conditions, prompt_message, is_active
                FROM rating_prompts
                WHERE is_active = TRUE
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def log_rating_prompt(self, session_id: str, prompt_id: int) -> int:
        """Log when rating prompt was shown"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                INSERT INTO rating_prompt_logs (session_id, prompt_id)
                VALUES (%s, %s)
                RETURNING id
            """, (session_id, prompt_id))
            return cursor.fetchone()["id"]
    
    # =========================================================================
    # FORM CONFIG FROM DATABASE
    # =========================================================================
    
    def get_form_config(self, config_key: str = None) -> Optional[Dict]:
        """Get form configuration from database"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            if config_key:
                cursor.execute("""
                    SELECT config_data FROM form_configs 
                    WHERE config_key = %s AND is_active = TRUE
                """, (config_key,))
            else:
                cursor.execute("""
                    SELECT config_data FROM form_configs 
                    WHERE is_active = TRUE 
                    ORDER BY updated_at DESC LIMIT 1
                """)
            
            row = cursor.fetchone()
            if row:
                return row["config_data"]
            return None
    
    def save_form_config(self, config_key: str, config_data: Dict, 
                         version: str = "1.0.0") -> int:
        """Save form configuration to database"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("UPDATE form_configs SET is_active = FALSE WHERE is_active = TRUE")
            
            cursor.execute("""
                INSERT INTO form_configs (config_key, config_data, version, is_active)
                VALUES (%s, %s, %s, TRUE)
                RETURNING id
            """, (config_key, json.dumps(config_data), version))
            
            return cursor.fetchone()["id"]
    
    def get_system_setting(self, setting_key: str) -> Optional[Dict]:
        """Get system setting"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT setting_value FROM system_settings WHERE setting_key = %s
            """, (setting_key,))
            row = cursor.fetchone()
            if row:
                return row["setting_value"]
            return None
    
    def update_system_setting(self, setting_key: str, setting_value: Dict) -> bool:
        """Update system setting"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO system_settings (setting_key, setting_value, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (setting_key) DO UPDATE SET
                    setting_value = EXCLUDED.setting_value,
                    updated_at = NOW()
            """, (setting_key, json.dumps(setting_value)))
            return True
    
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
                VALUES (%s, %s, %s, %s)
            """, (session_id, role, message, json.dumps(metadata) if metadata else None))
    
    def get_conversation_history(self, session_id: str, limit: int = 50) -> List[Dict]:
        """Get conversation history"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT * FROM conversation_logs 
                WHERE session_id = %s
                ORDER BY timestamp DESC LIMIT %s
            """, (session_id, limit))
            return [dict(row) for row in cursor.fetchall()][::-1]
    
    # =========================================================================
    # STATISTICS & CLEANUP
    # =========================================================================
    
    def get_registration_stats(self, user_id: str = None) -> Dict:
        """Get registration statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            if user_id:
                cursor.execute("""
                    SELECT status, COUNT(*) as count FROM registrations
                    WHERE user_id = %s
                    GROUP BY status
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT status, COUNT(*) as count FROM registrations
                    GROUP BY status
                """)
            
            status_counts = {row["status"]: row["count"] for row in cursor.fetchall()}
            
            if user_id:
                cursor.execute("""
                    SELECT COUNT(*) as count FROM registrations
                    WHERE user_id = %s AND DATE(created_at) = CURRENT_DATE
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT COUNT(*) as count FROM registrations
                    WHERE DATE(created_at) = CURRENT_DATE
                """)
            today = cursor.fetchone()["count"]
            
            if user_id:
                cursor.execute("""
                    SELECT COUNT(*) as count FROM registrations
                    WHERE user_id = %s AND created_at >= CURRENT_DATE - INTERVAL '7 days'
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT COUNT(*) as count FROM registrations
                    WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
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
    
    def cleanup_old_batches(self, days: int = 7) -> int:
        """Remove old upload batches"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM upload_batches 
                WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '%s days'
                AND status IN ('completed', 'failed', 'partial')
            """, (days,))
            return cursor.rowcount
    
    def close(self):
        """Close all connections in pool"""
        if self._pool:
            self._pool.closeall()


# =============================================================================
# SINGLETON
# =============================================================================

_db_manager: Optional[DatabaseManager] = None

def get_db_manager() -> DatabaseManager:
    """Get database manager singleton"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager

def init_database(database_url: str = None) -> DatabaseManager:
    """Initialize database with optional custom URL"""
    global _db_manager
    _db_manager = DatabaseManager(database_url=database_url)
    return _db_manager