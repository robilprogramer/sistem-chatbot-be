
# Panduan Mengelola Service Backend Sistem Chatbot

Dokumen ini berisi perintah-perintah penting untuk mengelola backend Sistem Chatbot yang dijalankan sebagai **systemd service**.

---

## 1. Cek Status Service

Untuk melihat apakah backend sedang berjalan:

```bash
sudo systemctl status sistem-chatbot-be.service
```

Contoh output yang normal:

```
Active: active (running)
Uvicorn running on http://0.0.0.0:8000
```

---

## 2. Matikan Service

Jika ingin menghentikan backend sementara:

```bash
sudo systemctl stop sistem-chatbot-be.service
```

Status service akan berubah menjadi `inactive (dead)`.

---

## 3. Jalankan Service

Untuk menyalakan service yang sebelumnya dimatikan:

```bash
sudo systemctl start sistem-chatbot-be.service
```

Service akan berjalan kembali di background.

---

## 4. Restart Service

Jika melakukan update kode atau konfigurasi, gunakan restart:

```bash
sudo systemctl restart sistem-chatbot-be.service
```

Service akan otomatis berhenti lalu dijalankan kembali.

---

## 5. Melihat Log Realtime

Untuk melihat log backend secara realtime:

```bash
journalctl -u sistem-chatbot-be.service -f
```

Gunakan ini untuk debugging atau memantau aktivitas server.

---

## 6. Tips Tambahan

- Setelah melakukan perubahan di file service (`.service`), jalankan:

```bash
sudo systemctl daemon-reload
```

Agar systemd membaca konfigurasi terbaru.

- Gunakan kombinasi `restart` + `journalctl -f` saat deploy untuk memantau server langsung.

---

Dokumen ini memudahkan manajemen backend Sistem Chatbot tanpa perlu selalu masuk ke folder project.
