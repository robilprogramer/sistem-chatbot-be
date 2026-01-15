# 📚 PANDUAN LENGKAP: Database Dynamic Config

## 🗂️ DAFTAR TABEL YANG DITAMBAHKAN

Total ada **12 tabel baru** yang perlu ditambahkan:

| No | Tabel | Fungsi | Isi |
|----|-------|--------|-----|
| 1 | `form_configs` | Menyimpan config utama (pengganti form_config.yaml) | JSON lengkap dari YAML |
| 2 | `form_steps` | Detail steps pendaftaran | school_selection, student_info, dll |
| 3 | `form_fields` | Detail semua field | nama_lengkap, tanggal_lahir, dll |
| 4 | `form_messages` | Template pesan | welcome, error messages, dll |
| 5 | `form_commands` | Command keywords | lanjut, kembali, reset, dll |
| 6 | `upload_batches` | Track batch upload | Untuk multiple file upload |
| 7 | `auto_triggers` | Config auto-message | Idle reminder, rating prompt |
| 8 | `trigger_logs` | Log triggered messages | History pesan otomatis |
| 9 | `session_activity` | Track user activity | Untuk idle detection |
| 10 | `ratings` | User ratings | Rating 1-5 + feedback |
| 11 | `rating_prompts` | Config rating prompts | Kapan minta rating |
| 12 | `system_settings` | System-wide settings | Config source, dll |

---

## 🔧 SETTING AWAL (Environment Variables)

Tambahkan di file `.env`:

```env
# =============================================================================
# DATABASE
# =============================================================================
DATABASE_URL=postgresql://user:password@localhost:5432/ypi_alazhar

# =============================================================================
# CONFIG SOURCE SETTINGS
# =============================================================================
# Pilih sumber config: 'yaml' atau 'database'
FORM_CONFIG_SOURCE=yaml

# Fallback jika source utama gagal
FORM_CONFIG_FALLBACK=yaml

# Auto sync YAML ke database saat startup (true/false)
FORM_CONFIG_AUTO_SYNC=false

# =============================================================================
# IDLE DETECTION
# =============================================================================
IDLE_CHECK_INTERVAL=60
DEFAULT_IDLE_MINUTES=5

# =============================================================================
# RATING
# =============================================================================
RATING_ENABLED=true
```

---

## 📊 CONTOH ISI SETIAP TABEL

### 1️⃣ form_configs
```sql
-- Tabel utama, menyimpan SELURUH config sebagai JSON
SELECT * FROM form_configs;

| id | config_key                    | config_type | config_data                  | version | is_active |
|----|-------------------------------|-------------|------------------------------|---------|-----------|
| 1  | form_config_20250114_120000   | yaml        | {"form": {...}, "steps":...} | 3.0.0   | true      |
```

**Kolom penting:**
- `config_data`: JSON lengkap dari form_config.yaml
- `is_active`: Hanya 1 yang aktif (true)

---

### 2️⃣ form_steps
```sql
SELECT * FROM form_steps WHERE config_id = 1;

| id | config_id | step_id          | step_name           | step_order | is_mandatory | can_skip | icon |
|----|-----------|------------------|---------------------|------------|--------------|----------|------|
| 1  | 1         | school_selection | Pilihan Sekolah     | 1          | true         | false    | 🏫   |
| 2  | 1         | student_info     | Data Siswa          | 2          | true         | false    | 👤   |
| 3  | 1         | parent_info      | Data Orang Tua/Wali | 3          | true         | false    | 👨‍👩‍👧 |
| 4  | 1         | academic_info    | Riwayat Akademik    | 4          | false        | true     | 📚   |
| 5  | 1         | documents        | Dokumen Pendukung   | 5          | true         | false    | 📄   |
| 6  | 1         | review           | Review & Konfirmasi | 6          | true         | false    | ✅   |
```

---

### 3️⃣ form_fields
```sql
SELECT field_id, step_id, field_label, field_type, is_mandatory 
FROM form_fields WHERE config_id = 1 LIMIT 10;

| field_id        | step_id          | field_label       | field_type | is_mandatory |
|-----------------|------------------|-------------------|------------|--------------|
| nama_sekolah    | school_selection | Nama Sekolah      | select     | true         |
| tingkatan       | school_selection | Tingkatan/Jenjang | select     | true         |
| program         | school_selection | Program           | select     | true         |
| nama_lengkap    | student_info     | Nama Lengkap      | text       | true         |
| nama_panggilan  | student_info     | Nama Panggilan    | text       | false        |
| tempat_lahir    | student_info     | Tempat Lahir      | text       | true         |
| tanggal_lahir   | student_info     | Tanggal Lahir     | date       | true         |
| jenis_kelamin   | student_info     | Jenis Kelamin     | select     | true         |
| alamat          | student_info     | Alamat Lengkap    | textarea   | true         |
| nama_ayah       | parent_info      | Nama Ayah         | text       | true         |
```

---

### 4️⃣ form_messages
```sql
SELECT message_key, LEFT(message_template, 50) as preview FROM form_messages LIMIT 10;

| message_key              | preview                                            |
|--------------------------|----------------------------------------------------|
| welcome                  | 👋 Selamat datang di Pendaftaran Siswa Baru...     |
| step_transitions.to_step | Mari lanjut ke tahap berikutnya...                 |
| confirmation.ask         | 📋 **RINGKASAN DATA PENDAFTARAN**...               |
| confirmation.not_sure    | Baik, silakan periksa dan ubah data...             |
| errors.validation        | ❌ Data tidak valid: {error}                       |
| registration_confirmed   | 🎉 **PENDAFTARAN BERHASIL!**...                    |
```

---

### 5️⃣ form_commands
```sql
SELECT * FROM form_commands WHERE config_id = 1;

| command_name   | keywords                                    | pattern                        |
|----------------|---------------------------------------------|--------------------------------|
| advance        | ["lanjut", "next", "skip", "lewati"]        | NULL                           |
| back           | ["back", "kembali", "sebelumnya"]           | NULL                           |
| summary        | ["summary", "ringkasan", "lihat data"]      | NULL                           |
| edit           | []                                          | (ubah\|ganti\|edit)\\s+(.+)    |
| confirm        | ["konfirmasi", "confirm", "selesai"]        | NULL                           |
| confirm_yes    | ["ya saya yakin", "ya yakin", "yakin"]      | NULL                           |
| reset          | ["ulang", "reset", "hapus semua"]           | NULL                           |
| help           | ["help", "bantuan", "tolong"]               | NULL                           |
```

---

### 6️⃣ auto_triggers
```sql
SELECT * FROM auto_triggers;

| id | trigger_name         | trigger_type  | conditions                              | message_template                    | priority | cooldown |
|----|----------------------|---------------|-----------------------------------------|-------------------------------------|----------|----------|
| 1  | idle_reminder        | idle          | {"idle_minutes": 5}                     | Hai! Jangan lupa lanjutkan...       | 10       | 10       |
| 2  | document_stuck       | step_stuck    | {"step": "documents", "stuck_minutes": 10} | Butuh bantuan upload dokumen?    | 8        | 15       |
| 3  | incomplete_reminder  | incomplete    | {"completion_below": 50}                | Data baru {completion}% lengkap...  | 5        | 30       |
| 4  | rating_after_complete| rating_prompt | {"after_completion": true}              | Terima kasih! Boleh berikan rating? | 15       | 60       |
```

---

### 7️⃣ system_settings
```sql
SELECT * FROM system_settings;

| setting_key        | setting_value                                                    |
|--------------------|------------------------------------------------------------------|
| form_config_source | {"source": "database", "fallback": "yaml", "auto_sync": true}   |
| idle_detection     | {"enabled": true, "check_interval_seconds": 60}                  |
| rating_system      | {"enabled": true, "prompt_after_completion": true}               |
| multiple_upload    | {"enabled": true, "max_files": 10, "max_batch_size_mb": 50}      |
```

---

## 🔄 SCENARIO: SWITCH CONFIG SOURCE

### Scenario 1: Awal Pakai YAML (Default)

```
.env:
FORM_CONFIG_SOURCE=yaml
FORM_CONFIG_FALLBACK=yaml
FORM_CONFIG_AUTO_SYNC=false

Alur:
1. App start → baca form_config.yaml
2. Semua config dari file YAML
3. Database TIDAK digunakan untuk config
```

### Scenario 2: Switch ke Database (Pertama Kali)

```bash
# Step 1: Ubah .env
FORM_CONFIG_SOURCE=yaml
FORM_CONFIG_AUTO_SYNC=true  # <-- Enable auto sync

# Step 2: Restart app
# App akan otomatis sync YAML → Database

# Step 3: Ubah .env lagi
FORM_CONFIG_SOURCE=database
FORM_CONFIG_AUTO_SYNC=false

# Step 4: Restart app
# Sekarang config dari Database
```

### Scenario 3: Switch via API (Runtime)

```bash
# Cek source saat ini
curl http://localhost:8000/api/transactional/v1/config/source
# Response: {"source": "yaml", "fallback": "yaml"}

# Sync YAML ke Database
curl -X POST http://localhost:8000/api/transactional/v1/config/sync/yaml-to-db
# Response: {"success": true, "message": "YAML synced to database"}

# Switch ke Database
curl -X POST http://localhost:8000/api/transactional/v1/config/switch \
  -d "source=database"
# Response: {"success": true, "source": "database"}
```

---

## ➕ SCENARIO: TAMBAH FIELD BARU

### Jika Pakai YAML:
```yaml
# Edit file config/form_config.yaml
fields:
  # ... existing fields ...
  
  # Tambah field baru
  nomor_kip:
    label: "Nomor KIP"
    step: "student_info"
    type: "text"
    is_mandatory: false
    tips: "Kartu Indonesia Pintar (jika ada)"
    examples:
      - "6123456789012345"
```

Lalu restart app.

### Jika Pakai Database:
```sql
-- Insert field baru langsung ke database
INSERT INTO form_fields 
(config_id, step_id, field_id, field_label, field_type, is_mandatory, tips, examples)
VALUES (
    1,  -- config_id aktif
    'student_info',
    'nomor_kip',
    'Nomor KIP',
    'text',
    false,
    'Kartu Indonesia Pintar (jika ada)',
    ARRAY['6123456789012345']
);
```

Lalu reload config:
```bash
curl -X POST http://localhost:8000/api/transactional/v1/config/reload
```

---

## ➕ SCENARIO: TAMBAH STEP BARU

### Jika Pakai Database:
```sql
-- 1. Insert step baru
INSERT INTO form_steps 
(config_id, step_id, step_name, description, step_order, is_mandatory, can_skip, icon)
VALUES (
    1,
    'health_info',
    'Informasi Kesehatan',
    'Data kesehatan dan riwayat penyakit',
    5,  -- setelah academic_info
    false,
    true,
    '🏥'
);

-- 2. Update order step setelahnya
UPDATE form_steps SET step_order = step_order + 1 
WHERE config_id = 1 AND step_order >= 5 AND step_id != 'health_info';

-- 3. Tambahkan fields untuk step baru
INSERT INTO form_fields 
(config_id, step_id, field_id, field_label, field_type, is_mandatory)
VALUES 
(1, 'health_info', 'golongan_darah', 'Golongan Darah', 'select', false),
(1, 'health_info', 'riwayat_penyakit', 'Riwayat Penyakit', 'textarea', false),
(1, 'health_info', 'alergi', 'Alergi', 'text', false);
```

---

## ➕ SCENARIO: UBAH AUTO-TRIGGER

```sql
-- Ubah waktu idle dari 5 menit jadi 3 menit
UPDATE auto_triggers 
SET conditions = '{"idle_minutes": 3}'::jsonb
WHERE trigger_name = 'idle_reminder';

-- Ubah message
UPDATE auto_triggers 
SET message_template = 'Halo! Masih di sana? Yuk lanjutkan pendaftaran! 😊'
WHERE trigger_name = 'idle_reminder';

-- Disable trigger tertentu
UPDATE auto_triggers 
SET is_active = false
WHERE trigger_name = 'incomplete_reminder';
```

---

## 📋 CHECKLIST IMPLEMENTASI

```
□ 1. Jalankan SQL migration (01_database_schema.sql)
□ 2. Set environment variables di .env
□ 3. Copy file-file Python baru
□ 4. Update main.py dengan startup events
□ 5. Test dengan FORM_CONFIG_SOURCE=yaml dulu
□ 6. Sync ke database: --populate atau via API
□ 7. Verify dengan: python populate_database.py --verify
□ 8. Switch ke database: FORM_CONFIG_SOURCE=database
□ 9. Test semua fitur
```

---

## ❓ FAQ

**Q: Apa bedanya form_configs.config_data dengan tabel detail (form_steps, form_fields)?**

A: `form_configs.config_data` menyimpan JSON lengkap sebagai backup/referensi. Tabel detail (`form_steps`, `form_fields`, dll) digunakan untuk query yang lebih efisien dan memungkinkan update per-record.

**Q: Kalau edit di database, apakah perlu update form_configs.config_data juga?**

A: Tidak wajib, tapi recommended untuk konsistensi. Atau bisa di-generate ulang dengan sync.

**Q: Bagaimana kalau database down?**

A: Sistem akan fallback ke YAML (sesuai setting `FORM_CONFIG_FALLBACK`).

**Q: Apakah bisa mix (sebagian dari YAML, sebagian dari DB)?**

A: Tidak, satu source saja yang aktif. Tapi bisa switch kapan saja.
