# 4.2.1 Pengujian Performa RAG

Pengujian performa RAG dilakukan untuk mengukur akurasi retrieval dan kualitas respons yang dihasilkan sistem.

**Tanggal Pengujian:** 2026-01-19 14:45:35


## Pengujian Retrieval Accuracy

Pengujian retrieval accuracy mengukur ketepatan sistem dalam mengambil dokumen yang relevan.

**Tabel 4.13 Hasil Pengujian Retrieval Accuracy**

| No | Query | Retrieved Docs | Relevant | Precision | Time (s) |
|:--:|-------|:--------------:|:--------:|:---------:|:--------:|
| 1 | Biaya Sekolah SD Al-Azhar Cibinong | 3 | 3 | 100.00% | 1.220 |
| 2 | Persyaratan pendaftaran SMP | 3 | 3 | 100.00% | 0.465 |
| 3 | Jadwal tahun ajaran baru | 3 | 3 | 100.00% | 0.415 |
| 4 | Fasilitas sekolah | 3 | 3 | 100.00% | 0.791 |
| 5 | Kurikulum yang digunakan | 3 | 0 | 0.00% | 0.639 |

**Rata-rata Precision:** 80.00%

**Rata-rata Response Time:** 0.706s


## Pengujian Response Quality

Pengujian response quality mengukur kualitas jawaban yang dihasilkan oleh chatbot.

Skala penilaian: 1 (Sangat Buruk) - 5 (Sangat Baik)

**Tabel 4.14 Hasil Pengujian Response Quality**

| No | Query | Relevance (1-5) | Accuracy (1-5) | Completeness (1-5) | Avg |
|:--:|-------|:---------------:|:--------------:|:------------------:|:---:|
| 1 | Berapa biaya pendaftaran untuk SD Cibinong Al-Azhar? | 5 | 5 | 4 | 4.67 |
| 2 | Apa saja dokumen yang diperlukan untuk mendaftar ke SD Al-Azhar? | 5 | 3 | 2 | 3.33 |
| 3 | Jelaskan program unggulan yang ada di SMP Al-Azhar | 4 | 3 | 2 | 3.00 |

**Rata-rata Keseluruhan:** 3.67/5.00


## Detail Jawaban Response Quality


### Query 1: Berapa biaya pendaftaran untuk SD Cibinong Al-Azhar?

**Jawaban:**

> Berdasarkan dokumen "Biaya - SD Islam Al Azhar 27 Cibinong Tahun Ajaran 2026-2027", biaya pendaftaran untuk SD Cibinong terdiri dari beberapa komponen. Pertama, Uang Formulir sebesar Rp 550.000, kedua, Uang Pangkal sebesar Rp 25.575.000, dan ketiga, Uang Sekolah sebesar Rp 1.425.000. Biaya ini berlaku untuk pendaftar yang berasal dari sekolah di luar lingkungan Al Azhar. Untuk informasi lebih lanjut, calon pendaftar dapat menghubungi bagian pendaftaran di SD Islam Al Azhar 27 Cibinong.


**Jumlah Sumber:** 3

**Rata-rata Similarity:** 0.857


### Query 2: Apa saja dokumen yang diperlukan untuk mendaftar ke SD Al-Azhar?

**Jawaban:**

> Maaf, saya tidak menemukan informasi tentang dokumen yang diperlukan untuk mendaftar ke SD Al-Azhar dalam database saya.


**Jumlah Sumber:** 3

**Rata-rata Similarity:** 0.817


### Query 3: Jelaskan program unggulan yang ada di SMP Al-Azhar

**Jawaban:**

> Maaf, saya tidak menemukan informasi tentang program unggulan di SMP Al-Azhar dalam database saya.


**Jumlah Sumber:** 3

**Rata-rata Similarity:** 0.759


## Kesimpulan Pengujian

1. **Retrieval Accuracy:** Rata-rata precision mencapai 80.00% dengan waktu respons rata-rata 0.706 detik.

2. **Response Quality:** Rata-rata skor kualitas respons adalah 3.67/5.00.
