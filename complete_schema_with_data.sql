-- =============================================================================
-- COMPLETE DATABASE SCHEMA + SAMPLE DATA
-- YPI Al-Azhar Chatbot - Dynamic Config System
-- =============================================================================
-- 
-- CARA PAKAI:
-- psql -U postgres -d ypi_alazhar -f complete_schema_with_data.sql
--
-- =============================================================================

-- =============================================================================
-- PART 1: CREATE TABLES (12 tabel baru)
-- =============================================================================

-- 1. form_configs - Menyimpan config utama (JSON)
CREATE TABLE IF NOT EXISTS form_configs (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(100) UNIQUE NOT NULL,
    config_type VARCHAR(50) NOT NULL DEFAULT 'yaml',
    config_data JSONB NOT NULL,
    version VARCHAR(20) NOT NULL DEFAULT '1.0.0',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    notes TEXT
);

-- 2. form_steps - Detail steps pendaftaran
CREATE TABLE IF NOT EXISTS form_steps (
    id SERIAL PRIMARY KEY,
    config_id INTEGER REFERENCES form_configs(id) ON DELETE CASCADE,
    step_id VARCHAR(100) NOT NULL,
    step_name VARCHAR(255) NOT NULL,
    description TEXT,
    step_order INTEGER NOT NULL,
    is_mandatory BOOLEAN DEFAULT true,
    can_skip BOOLEAN DEFAULT false,
    skip_conditions JSONB,
    icon VARCHAR(10),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(config_id, step_id)
);

-- 3. form_fields - Detail semua field input
CREATE TABLE IF NOT EXISTS form_fields (
    id SERIAL PRIMARY KEY,
    config_id INTEGER REFERENCES form_configs(id) ON DELETE CASCADE,
    step_id VARCHAR(100) NOT NULL,
    field_id VARCHAR(100) NOT NULL,
    field_label VARCHAR(255) NOT NULL,
    field_type VARCHAR(50) NOT NULL DEFAULT 'text',
    is_mandatory BOOLEAN DEFAULT false,
    validation JSONB,
    options JSONB,
    examples TEXT[],
    tips TEXT,
    extract_keywords TEXT[],
    auto_formats JSONB,
    auto_clean BOOLEAN DEFAULT false,
    default_value TEXT,
    field_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(config_id, field_id)
);

-- 4. form_messages - Template pesan bot
CREATE TABLE IF NOT EXISTS form_messages (
    id SERIAL PRIMARY KEY,
    config_id INTEGER REFERENCES form_configs(id) ON DELETE CASCADE,
    message_key VARCHAR(255) NOT NULL,
    message_template TEXT NOT NULL,
    language VARCHAR(10) DEFAULT 'id',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(config_id, message_key, language)
);

-- 5. form_commands - Keyword commands
CREATE TABLE IF NOT EXISTS form_commands (
    id SERIAL PRIMARY KEY,
    config_id INTEGER REFERENCES form_configs(id) ON DELETE CASCADE,
    command_name VARCHAR(100) NOT NULL,
    keywords TEXT[] NOT NULL,
    pattern TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(config_id, command_name)
);

-- 6. upload_batches - Track multiple file uploads
CREATE TABLE IF NOT EXISTS upload_batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,
    field_name VARCHAR(100),
    total_files INTEGER DEFAULT 0,
    uploaded_files INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- 7. auto_triggers - Config untuk auto-message
CREATE TABLE IF NOT EXISTS auto_triggers (
    id SERIAL PRIMARY KEY,
    trigger_name VARCHAR(100) UNIQUE NOT NULL,
    trigger_type VARCHAR(50) NOT NULL,
    conditions JSONB NOT NULL,
    message_template TEXT NOT NULL,
    priority INTEGER DEFAULT 0,
    max_triggers_per_session INTEGER DEFAULT 3,
    cooldown_minutes INTEGER DEFAULT 10,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. trigger_logs - Log auto-messages yang terkirim
CREATE TABLE IF NOT EXISTS trigger_logs (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    trigger_id INTEGER REFERENCES auto_triggers(id),
    trigger_name VARCHAR(100),
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    message_sent TEXT,
    user_responded BOOLEAN DEFAULT false,
    response_at TIMESTAMP
);

-- 9. session_activity - Track aktivitas user (untuk idle detection)
CREATE TABLE IF NOT EXISTS session_activity (
    id SERIAL PRIMARY KEY,
    session_id TEXT UNIQUE NOT NULL,
    user_id TEXT,
    last_activity_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_message_at TIMESTAMP,
    current_step VARCHAR(100),
    completion_percentage REAL DEFAULT 0,
    is_idle BOOLEAN DEFAULT false,
    idle_since TIMESTAMP,
    total_idle_triggers INTEGER DEFAULT 0
);

-- 10. ratings - User ratings
CREATE TABLE IF NOT EXISTS ratings (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT,
    registration_number VARCHAR(100),
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    feedback_text TEXT,
    rating_category VARCHAR(50) DEFAULT 'overall',
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 11. rating_prompts - Config kapan minta rating
CREATE TABLE IF NOT EXISTS rating_prompts (
    id SERIAL PRIMARY KEY,
    prompt_type VARCHAR(50) NOT NULL,
    conditions JSONB,
    prompt_message TEXT NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 12. system_settings - System-wide settings
CREATE TABLE IF NOT EXISTS system_settings (
    id SERIAL PRIMARY KEY,
    setting_key VARCHAR(100) UNIQUE NOT NULL,
    setting_value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100)
);

-- Update existing documents table (jika ada)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'documents') THEN
        ALTER TABLE documents ADD COLUMN IF NOT EXISTS upload_batch_id UUID;
        ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_order INTEGER DEFAULT 0;
        ALTER TABLE documents ADD COLUMN IF NOT EXISTS is_primary BOOLEAN DEFAULT false;
        ALTER TABLE documents ADD COLUMN IF NOT EXISTS metadata JSONB;
    END IF;
END $$;

-- =============================================================================
-- PART 2: CREATE INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_form_steps_config ON form_steps(config_id);
CREATE INDEX IF NOT EXISTS idx_form_fields_config ON form_fields(config_id);
CREATE INDEX IF NOT EXISTS idx_form_fields_step ON form_fields(step_id);
CREATE INDEX IF NOT EXISTS idx_form_messages_config ON form_messages(config_id);
CREATE INDEX IF NOT EXISTS idx_upload_batch_session ON upload_batches(session_id);
CREATE INDEX IF NOT EXISTS idx_trigger_log_session ON trigger_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_session_activity_idle ON session_activity(is_idle, last_activity_at);
CREATE INDEX IF NOT EXISTS idx_rating_session ON ratings(session_id);
CREATE INDEX IF NOT EXISTS idx_rating_created ON ratings(created_at);

-- =============================================================================
-- PART 3: INSERT SAMPLE DATA
-- =============================================================================

-- 3.1 System Settings
INSERT INTO system_settings (setting_key, setting_value, description) VALUES
('form_config_source', 
 '{"source": "database", "fallback": "yaml", "auto_sync": true}',
 'Source for form configuration: yaml or database'),
('idle_detection', 
 '{"enabled": true, "check_interval_seconds": 60, "default_idle_minutes": 5}',
 'Idle detection settings'),
('rating_system', 
 '{"enabled": true, "prompt_after_completion": true, "prompt_on_idle_exit": true}',
 'Rating system settings'),
('multiple_upload', 
 '{"enabled": true, "max_files": 10, "max_batch_size_mb": 50}',
 'Multiple file upload settings')
ON CONFLICT (setting_key) DO UPDATE SET
    setting_value = EXCLUDED.setting_value,
    updated_at = CURRENT_TIMESTAMP;

-- 3.2 Auto Triggers
INSERT INTO auto_triggers (trigger_name, trigger_type, conditions, message_template, priority, max_triggers_per_session, cooldown_minutes) VALUES
('idle_reminder', 'idle', 
 '{"idle_minutes": 5}',
 'Hai! Sepertinya kamu sedang sibuk. Jangan lupa lanjutkan pendaftaran ya! 😊

Kamu sudah mengisi {completion}% data. Ketik "lanjut" untuk melanjutkan.',
 10, 2, 10),

('document_stuck', 'step_stuck', 
 '{"step": "documents", "stuck_minutes": 10}',
 'Butuh bantuan upload dokumen? 📄

Tips:
• Kamu bisa upload beberapa file sekaligus
• Format yang diterima: PDF, JPG, PNG
• Maksimal 5MB per file

Ketik "bantuan" jika perlu panduan.',
 8, 1, 15),

('incomplete_reminder', 'incomplete', 
 '{"completion_below": 50, "idle_minutes": 15}',
 'Data pendaftaran kamu baru {completion}% lengkap.

Yuk selesaikan! Ketik "lanjut" untuk melanjutkan. 💪',
 5, 1, 30),

('rating_after_complete', 'rating_prompt', 
 '{"after_completion": true}',
 'Terima kasih telah menyelesaikan pendaftaran! 🎉

Boleh minta waktu sebentar untuk memberikan rating pengalaman kamu?

⭐ Ketik angka 1-5 (1=Buruk, 5=Sangat Baik)',
 15, 1, 60)
ON CONFLICT (trigger_name) DO UPDATE SET
    conditions = EXCLUDED.conditions,
    message_template = EXCLUDED.message_template;

-- 3.3 Rating Prompts
INSERT INTO rating_prompts (prompt_type, conditions, prompt_message) VALUES
('post_registration', 
 '{"after_completion": true}',
 '🌟 **Bagaimana pengalaman kamu?**

Berikan rating untuk pelayanan chatbot pendaftaran kami:

⭐ 1 - Sangat Tidak Puas
⭐⭐ 2 - Tidak Puas
⭐⭐⭐ 3 - Cukup
⭐⭐⭐⭐ 4 - Puas
⭐⭐⭐⭐⭐ 5 - Sangat Puas

Ketik angka 1-5 untuk memberikan rating.'),

('idle_exit', 
 '{"idle_minutes": 30, "min_messages": 3}',
 'Sepertinya kamu akan pergi. Boleh berikan rating sebelum pergi?

Ketik angka 1-5:
1️⃣ Buruk | 2️⃣ Kurang | 3️⃣ Cukup | 4️⃣ Bagus | 5️⃣ Sangat Bagus')
ON CONFLICT DO NOTHING;

-- =============================================================================
-- PART 4: SAMPLE FORM CONFIG (MINIMAL)
-- =============================================================================
-- Note: Ini adalah config minimal. Untuk config lengkap, gunakan:
-- python populate_database.py --populate config/form_config.yaml

INSERT INTO form_configs (config_key, config_type, config_data, version, is_active) VALUES
('form_config_initial', 'yaml', '{
  "form": {
    "id": "student_registration",
    "name": "Pendaftaran Siswa Baru YPI Al-Azhar",
    "version": "3.0.0"
  }
}', '3.0.0', true)
ON CONFLICT (config_key) DO NOTHING;

-- Get the config_id for inserting steps and fields
DO $$
DECLARE
    v_config_id INTEGER;
BEGIN
    SELECT id INTO v_config_id FROM form_configs WHERE is_active = true LIMIT 1;
    
    IF v_config_id IS NOT NULL THEN
        -- Insert Steps
        INSERT INTO form_steps (config_id, step_id, step_name, description, step_order, is_mandatory, can_skip, icon) VALUES
        (v_config_id, 'school_selection', 'Pilihan Sekolah', 'Pilih sekolah dan program yang dituju', 1, true, false, '🏫'),
        (v_config_id, 'student_info', 'Data Siswa', 'Informasi lengkap calon siswa', 2, true, false, '👤'),
        (v_config_id, 'parent_info', 'Data Orang Tua/Wali', 'Informasi orang tua atau wali', 3, true, false, '👨‍👩‍👧'),
        (v_config_id, 'academic_info', 'Riwayat Akademik', 'Informasi sekolah sebelumnya dan nilai rapor', 4, false, true, '📚'),
        (v_config_id, 'documents', 'Dokumen Pendukung', 'Upload dokumen yang diperlukan', 5, true, false, '📄'),
        (v_config_id, 'review', 'Review & Konfirmasi', 'Tinjau dan konfirmasi data', 6, true, false, '✅')
        ON CONFLICT (config_id, step_id) DO NOTHING;
        
        -- Insert Sample Fields (minimal)
        INSERT INTO form_fields (config_id, step_id, field_id, field_label, field_type, is_mandatory, field_order) VALUES
        -- School Selection
        (v_config_id, 'school_selection', 'nama_sekolah', 'Nama Sekolah', 'select', true, 1),
        (v_config_id, 'school_selection', 'tingkatan', 'Tingkatan/Jenjang', 'select', true, 2),
        (v_config_id, 'school_selection', 'program', 'Program', 'select', true, 3),
        -- Student Info
        (v_config_id, 'student_info', 'nama_lengkap', 'Nama Lengkap', 'text', true, 1),
        (v_config_id, 'student_info', 'tempat_lahir', 'Tempat Lahir', 'text', true, 2),
        (v_config_id, 'student_info', 'tanggal_lahir', 'Tanggal Lahir', 'date', true, 3),
        (v_config_id, 'student_info', 'jenis_kelamin', 'Jenis Kelamin', 'select', true, 4),
        (v_config_id, 'student_info', 'alamat', 'Alamat Lengkap', 'textarea', true, 5),
        -- Parent Info
        (v_config_id, 'parent_info', 'nama_ayah', 'Nama Ayah', 'text', true, 1),
        (v_config_id, 'parent_info', 'nama_ibu', 'Nama Ibu', 'text', true, 2),
        (v_config_id, 'parent_info', 'no_hp_ortu', 'No. HP Orang Tua', 'phone', true, 3),
        (v_config_id, 'parent_info', 'email_ortu', 'Email Orang Tua', 'email', true, 4),
        -- Documents
        (v_config_id, 'documents', 'foto_siswa', 'Foto Siswa', 'file', true, 1),
        (v_config_id, 'documents', 'akta_kelahiran', 'Akta Kelahiran', 'file', true, 2),
        (v_config_id, 'documents', 'kartu_keluarga', 'Kartu Keluarga', 'file', true, 3)
        ON CONFLICT (config_id, field_id) DO NOTHING;
        
        -- Insert Commands
        INSERT INTO form_commands (config_id, command_name, keywords, pattern) VALUES
        (v_config_id, 'advance', ARRAY['lanjut', 'next', 'skip', 'lewati', 'lanjutkan'], NULL),
        (v_config_id, 'back', ARRAY['back', 'kembali', 'sebelumnya', 'mundur'], NULL),
        (v_config_id, 'summary', ARRAY['summary', 'ringkasan', 'lihat data', 'data saya'], NULL),
        (v_config_id, 'confirm', ARRAY['konfirmasi', 'confirm', 'selesai', 'submit'], NULL),
        (v_config_id, 'confirm_yes', ARRAY['ya saya yakin', 'ya yakin', 'yakin', 'iya yakin'], NULL),
        (v_config_id, 'confirm_no', ARRAY['belum', 'tidak yakin', 'ragu', 'cancel'], NULL),
        (v_config_id, 'reset', ARRAY['ulang', 'reset', 'hapus semua', 'mulai ulang'], NULL),
        (v_config_id, 'help', ARRAY['help', 'bantuan', 'tolong', 'cara'], NULL)
        ON CONFLICT (config_id, command_name) DO NOTHING;
        
        -- Insert Messages
        INSERT INTO form_messages (config_id, message_key, message_template) VALUES
        (v_config_id, 'welcome', '👋 **Selamat datang di Pendaftaran Siswa Baru YPI Al-Azhar!**

Saya akan membantu proses pendaftaran. Mari mulai dengan memilih sekolah tujuan.

Silakan sebutkan:
• Nama sekolah
• Jenjang (TK/SD/SMP/SMA)
• Program yang diminati'),
        (v_config_id, 'confirmation.ask', '📋 **RINGKASAN DATA PENDAFTARAN**

Apakah data sudah benar? Ketik "ya saya yakin" untuk konfirmasi.'),
        (v_config_id, 'registration_confirmed', '🎉 **PENDAFTARAN BERHASIL!**

Nomor Registrasi: {registration_number}

Simpan nomor ini untuk cek status pendaftaran.')
        ON CONFLICT (config_id, message_key, language) DO NOTHING;
        
    END IF;
END $$;

-- =============================================================================
-- PART 5: VERIFICATION QUERY
-- =============================================================================

-- Run this to verify installation
DO $$
DECLARE
    r RECORD;
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '✅ DATABASE SETUP COMPLETE!';
    RAISE NOTICE '================================';
    
    FOR r IN 
        SELECT 'form_configs' as tbl, COUNT(*) as cnt FROM form_configs
        UNION ALL SELECT 'form_steps', COUNT(*) FROM form_steps
        UNION ALL SELECT 'form_fields', COUNT(*) FROM form_fields
        UNION ALL SELECT 'form_messages', COUNT(*) FROM form_messages
        UNION ALL SELECT 'form_commands', COUNT(*) FROM form_commands
        UNION ALL SELECT 'auto_triggers', COUNT(*) FROM auto_triggers
        UNION ALL SELECT 'rating_prompts', COUNT(*) FROM rating_prompts
        UNION ALL SELECT 'system_settings', COUNT(*) FROM system_settings
    LOOP
        RAISE NOTICE '  % : % rows', r.tbl, r.cnt;
    END LOOP;
    
    RAISE NOTICE '================================';
END $$;
