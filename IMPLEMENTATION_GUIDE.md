# Panduan Implementasi Fitur Baru
## YPI Al-Azhar Chatbot - Upgrade Features

---

## 📋 Daftar Fitur yang Diimplementasi

1. **Multiple File Upload** - Upload banyak file sekaligus
2. **Dynamic Config Source** - Switch antara YAML dan PostgreSQL database
3. **Auto-Trigger Messages** - Bot otomatis kirim pesan jika user idle
4. **Rating System** - Sistem rating dan feedback dari user

---

## 🚀 Langkah-Langkah Implementasi

### Step 1: Database Schema Migration

Jalankan SQL migration di PostgreSQL:

```bash
psql -U your_user -d your_database -f 01_database_schema.sql
```

**Atau jalankan query manual:**

```sql
-- Lihat file 01_database_schema.sql untuk schema lengkap
-- Tabel baru:
-- - form_configs: Menyimpan konfigurasi form dari YAML
-- - form_steps: Steps dari form
-- - form_fields: Field definitions
-- - form_messages: Message templates
-- - form_commands: Command configurations
-- - upload_batches: Track batch upload
-- - auto_triggers: Auto-trigger configurations
-- - trigger_logs: Log triggered messages
-- - session_activity: Track user activity untuk idle detection
-- - ratings: User ratings
-- - rating_prompts: Rating prompt configurations
-- - system_settings: System-wide settings
```

### Step 2: Install Dependencies

```bash
pip install sqlalchemy psycopg2-binary asyncio
```

### Step 3: Copy New Files

1. **config_loader.py** → `transaksional/app/config_loader.py`
2. **file_storage_enhanced.py** → `transaksional/app/file_storage_enhanced.py`
3. **auto_trigger.py** → `transaksional/app/auto_trigger.py`
4. **rating_system.py** → `transaksional/app/rating_system.py`
5. **transaksional_chat_router_enhanced.py** → `transaksional/app/transaksional_chat_router.py` (replace)
6. **database_extensions.py** → Tambahkan methods ke `database.py`

### Step 4: Update Environment Variables

Tambahkan di `.env`:

```env
# Config source: 'yaml' atau 'database'
FORM_CONFIG_SOURCE=yaml
FORM_CONFIG_FALLBACK=yaml
FORM_CONFIG_AUTO_SYNC=false

# PostgreSQL (untuk config dari database)
DATABASE_URL=postgresql://user:password@localhost:5432/ypi_alazhar

# Idle detection settings
IDLE_CHECK_INTERVAL=60
DEFAULT_IDLE_MINUTES=5

# Rating settings
RATING_ENABLED=true
```

### Step 5: Update Main Application

```python
# main.py
from fastapi import FastAPI
from transaksional.app.transaksional_chat_router import router as chat_router
from transaksional.app.auto_trigger import get_trigger_manager, init_trigger_manager
from transaksional.app.rating_system import init_rating_manager
from transaksional.app.database import get_db_manager

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    # Initialize database
    db = get_db_manager()
    
    # Initialize auto-trigger with background checker
    trigger_manager = init_trigger_manager(db_manager=db)
    trigger_manager.start_background_checker()
    
    # Initialize rating manager
    init_rating_manager(db_manager=db)

@app.on_event("shutdown")
async def shutdown_event():
    # Stop background checker
    trigger_manager = get_trigger_manager()
    trigger_manager.stop_background_checker()

# Include router
app.include_router(chat_router)
```

---

## 📁 Struktur File Baru

```
transaksional/
├── app/
│   ├── config.py                    # Keep as-is (backward compatible)
│   ├── config_loader.py             # NEW: Dynamic config loader
│   ├── database.py                  # UPDATE: Add extension methods
│   ├── database_extensions.py       # NEW: Extension methods reference
│   ├── file_storage.py              # Keep as-is atau ganti
│   ├── file_storage_enhanced.py     # NEW: Multiple file upload
│   ├── auto_trigger.py              # NEW: Idle detection & auto messages
│   ├── rating_system.py             # NEW: Rating system
│   ├── transaksional_chat_router.py # UPDATE: Enhanced router
│   ├── chat_handler.py              # Minor updates needed
│   ├── form_manager.py              # Minor updates needed
│   └── session_state.py             # Keep as-is
├── config/
│   ├── app_config.yaml              # Keep as-is
│   └── form_config.yaml             # Keep as-is (bisa di-sync ke DB)
└── main.py                          # UPDATE: Add startup events
```

---

## 🔧 API Endpoints Baru

### Multiple File Upload

```http
POST /api/transactional/v1/upload/multiple
Content-Type: multipart/form-data

session_id: string
file_type: string (e.g., "rapor_terakhir")
files: File[] (multiple files)
user_id: string (optional)
```

**Response:**
```json
{
  "session_id": "...",
  "batch_id": "uuid",
  "status": "completed|partial|failed",
  "total_files": 5,
  "successful_files": 4,
  "failed_files": 1,
  "results": [...],
  "errors": ["File X terlalu besar"],
  "message": "✅ Berhasil upload 4 file"
}
```

### Rating

```http
POST /api/transactional/v1/rating
Content-Type: application/json

{
  "session_id": "...",
  "rating": 5,
  "feedback": "Sangat membantu!",
  "user_id": "..."
}
```

```http
GET /api/transactional/v1/rating/stats
```

### Config Management

```http
GET /api/transactional/v1/config/source
# Response: {"source": "yaml", "fallback": "yaml"}

POST /api/transactional/v1/config/switch
# Body: source=database

POST /api/transactional/v1/config/sync/yaml-to-db
# Sync YAML config ke database

POST /api/transactional/v1/config/reload
# Reload semua config
```

### Session Activity

```http
GET /api/transactional/v1/session/{session_id}/activity
# Get session activity info

GET /api/transactional/v1/triggers/stats
# Get auto-trigger statistics
```

---

## ⚙️ Konfigurasi Auto-Trigger

Auto-trigger bisa dikonfigurasi melalui database atau config default:

```python
# Default triggers (di auto_trigger.py)
DEFAULT_TRIGGERS = [
    {
        "name": "idle_reminder",
        "trigger_type": "idle",
        "conditions": {"idle_minutes": 5},
        "message_template": "Hai! Jangan lupa lanjutkan pendaftaran...",
        "max_triggers_per_session": 2,
        "cooldown_minutes": 10
    },
    {
        "name": "rating_after_complete",
        "trigger_type": "rating_prompt",
        "conditions": {"after_completion": True},
        "message_template": "Terima kasih! Boleh berikan rating?",
        "max_triggers_per_session": 1
    }
]
```

**Trigger Types:**
- `idle` - User tidak chat dalam X menit
- `step_stuck` - User stuck di step tertentu
- `incomplete` - Completion di bawah X%
- `rating_prompt` - Minta rating setelah selesai

---

## 🔄 Switch Config Source

**Dari YAML ke Database:**

1. Set environment variable:
   ```env
   FORM_CONFIG_SOURCE=yaml
   FORM_CONFIG_AUTO_SYNC=true
   ```

2. Restart application → Config akan di-sync ke DB

3. Switch ke database:
   ```env
   FORM_CONFIG_SOURCE=database
   ```

**Atau via API:**
```bash
# Sync YAML ke DB
curl -X POST http://localhost:8000/api/transactional/v1/config/sync/yaml-to-db

# Switch source
curl -X POST http://localhost:8000/api/transactional/v1/config/switch \
  -d "source=database"
```

---

## 📊 Frontend Integration

### Multiple File Upload (React/Next.js)

```tsx
const uploadMultipleFiles = async (files: File[], sessionId: string, fileType: string) => {
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('file_type', fileType);
  
  files.forEach(file => {
    formData.append('files', file);
  });
  
  const response = await fetch('/api/transactional/v1/upload/multiple', {
    method: 'POST',
    body: formData
  });
  
  return response.json();
};

// Usage
<input
  type="file"
  multiple
  accept=".pdf,.jpg,.jpeg,.png"
  onChange={(e) => {
    const files = Array.from(e.target.files || []);
    uploadMultipleFiles(files, sessionId, 'rapor_terakhir');
  }}
/>
```

### Rating Component

```tsx
const RatingComponent = ({ sessionId, onSubmit }) => {
  const [rating, setRating] = useState(0);
  const [feedback, setFeedback] = useState('');

  const submitRating = async () => {
    const response = await fetch('/api/transactional/v1/rating', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        rating,
        feedback
      })
    });
    
    if (response.ok) {
      onSubmit();
    }
  };

  return (
    <div>
      <div className="stars">
        {[1, 2, 3, 4, 5].map(star => (
          <button
            key={star}
            onClick={() => setRating(star)}
            className={star <= rating ? 'active' : ''}
          >
            ⭐
          </button>
        ))}
      </div>
      <textarea
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        placeholder="Masukkan feedback (opsional)"
      />
      <button onClick={submitRating}>Submit Rating</button>
    </div>
  );
};
```

### WebSocket untuk Auto-Messages

```tsx
useEffect(() => {
  const ws = new WebSocket(`ws://localhost:8000/ws/${sessionId}`);
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.type === 'auto_message') {
      // Display auto-triggered message
      addMessage({
        role: 'assistant',
        content: data.message,
        isAutoMessage: true
      });
    }
  };

  return () => ws.close();
}, [sessionId]);
```

---

## 🧪 Testing

### Test Multiple Upload

```bash
curl -X POST http://localhost:8000/api/transactional/v1/upload/multiple \
  -F "session_id=test-123" \
  -F "file_type=rapor_terakhir" \
  -F "files=@file1.pdf" \
  -F "files=@file2.pdf" \
  -F "files=@file3.jpg"
```

### Test Rating

```bash
curl -X POST http://localhost:8000/api/transactional/v1/rating \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-123", "rating": 5, "feedback": "Sangat membantu!"}'
```

### Test Config Switch

```bash
# Get current source
curl http://localhost:8000/api/transactional/v1/config/source

# Sync to DB
curl -X POST http://localhost:8000/api/transactional/v1/config/sync/yaml-to-db

# Switch to DB
curl -X POST http://localhost:8000/api/transactional/v1/config/switch \
  -d "source=database"
```

---

## ❓ FAQ

**Q: Bagaimana jika database tidak tersedia saat pakai config dari DB?**
A: Sistem akan otomatis fallback ke YAML jika database tidak bisa diakses.

**Q: Apakah auto-trigger aman untuk production?**
A: Ya, ada proteksi seperti max triggers per session dan cooldown period.

**Q: Bagaimana reset rating flow jika user tidak jadi memberikan rating?**
A: Rating flow otomatis expired setelah session baru atau user mengirim pesan non-rating.

**Q: Apakah bisa custom message untuk auto-trigger?**
A: Ya, bisa via database table `auto_triggers` atau config default di code.

---

## 📞 Support

Jika ada pertanyaan atau masalah dalam implementasi, silakan hubungi atau buat issue di repository.
