# 4.2.1 Pengujian Performa RAG

Pengujian performa RAG dilakukan untuk mengukur akurasi retrieval dan kualitas respons yang dihasilkan sistem.

**Tanggal Pengujian:** 2026-02-08 11:30:32


## Pengujian Retrieval Accuracy

Pengujian retrieval accuracy mengukur ketepatan sistem dalam mengambil dokumen yang relevan.

**Tabel 4.13 Hasil Pengujian Retrieval Accuracy**

| No | Query | Retrieved Docs | Relevant | Precision | Time (s) |
|:--:|-------|:--------------:|:--------:|:---------:|:--------:|
| 1 | Biaya Sekolah SD Al-Azhar Cibinong | 3 | 3 | 100.00% | 0.907 |
| 2 | Persyaratan pendaftaran | 3 | 3 | 100.00% | 0.335 |
| 3 | Jadwal Pendaftaran | 3 | 3 | 100.00% | 0.228 |
| 4 | Fasilitas sekolah | 3 | 3 | 100.00% | 0.217 |
| 5 | Kurikulum yang digunakan | 3 | 3 | 100.00% | 0.212 |

**Rata-rata Precision:** 100.00%

**Rata-rata Response Time:** 0.380s


## Pengujian Response Quality

Pengujian response quality mengukur kualitas jawaban yang dihasilkan oleh chatbot.

Skala penilaian: 1 (Sangat Buruk) - 5 (Sangat Baik)

**Tabel 4.14 Hasil Pengujian Response Quality**

| No | Query | Relevance (1-5) | Accuracy (1-5) | Completeness (1-5) | Avg |
|:--:|-------|:---------------:|:--------------:|:------------------:|:---:|
| 1 | Berapa biaya pendaftaran untuk SD Cibinong Al-Azhar? | 5 | 5 | 4 | 4.67 |
| 2 | Apa saja dokumen yang diperlukan untuk mendaftar ke SD Al-Azhar? | 5 | 5 | 5 | 5.00 |
| 3 | Jelaskan program unggulan yang ada di SMP Al-Azhar | 4 | 3 | 2 | 3.00 |

**Rata-rata Keseluruhan:** 4.22/5.00


## Detail Jawaban Response Quality


### Query 1: Berapa biaya pendaftaran untuk SD Cibinong Al-Azhar?

**Jawaban:**

> Berdasarkan dokumen "Biaya - SD Islam Al Azhar 27 Cibinong Tahun Ajaran 2026-2027", biaya pendaftaran untuk SD Cibinong terdiri dari beberapa komponen. Pertama, Uang Formulir sebesar Rp 550.000, kedua, Uang Pangkal sebesar Rp 25.575.000, dan ketiga, Uang Sekolah sebesar Rp 1.425.000. Biaya ini berlaku untuk pendaftar yang berasal dari sekolah di luar lingkungan Al Azhar. Untuk informasi lebih lanjut, calon pendaftar dapat menghubungi bagian pendaftaran di SD Islam Al Azhar 27 Cibinong.


**Jumlah Sumber:** 3

**Rata-rata Similarity:** 0.857


### Query 2: Apa saja dokumen yang diperlukan untuk mendaftar ke SD Al-Azhar?

**Jawaban:**

> Berdasarkan dokumen "Persyaratan Dokumen Pendaftaran SD Al-Azhar", terdapat beberapa dokumen yang wajib disiapkan untuk mendaftar di Sekolah Dasar Al-Azhar, antara lain:

1. Salinan akta kelahiran calon peserta didik.
2. Kartu Keluarga (KK).
3. Pas foto terbaru calon peserta didik.
4. Formulir pendaftaran yang telah diisi lengkap.
5. Salinan KTP orang tua atau wali.
6. Surat keterangan dari Taman Kanak-Kanak (TK) atau Pendidikan Anak Usia Dini (PAUD) jika calon peserta didik sebelumnya telah men...


**Jumlah Sumber:** 3

**Rata-rata Similarity:** 0.847


### Query 3: Jelaskan program unggulan yang ada di SMP Al-Azhar

**Jawaban:**

> Maaf, saya tidak menemukan informasi tentang program unggulan di SMP Al-Azhar dalam database saya.


**Jumlah Sumber:** 3

**Rata-rata Similarity:** 0.798


## Kesimpulan Pengujian

1. **Retrieval Accuracy:** Rata-rata precision mencapai 100.00% dengan waktu respons rata-rata 0.380 detik.

2. **Response Quality:** Rata-rata skor kualitas respons adalah 4.22/5.00.
