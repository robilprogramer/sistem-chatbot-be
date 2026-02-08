# Pengujian Performa RAG - Query Biaya Sekolah

**Tanggal Pengujian:** 2026-02-08 14:21:31

**Fokus:** Query Informational tentang Biaya Sekolah Al Azhar

---


## Executive Summary

- **Total Query:** 40 (Informational Only)

- **Precision@3:** 96.7%

- **Recall@3:** 97.5%

- **Avg Response Time:** 0.232s

- **Response Quality:** 4.17/5.00


## Pengujian Retrieval Accuracy


### Hasil Per Kategori Query


#### A. Query Biaya Sekolah

- Jumlah Query: 14

- Precision@3: 100.0%

- Recall@3: 100.0%

- Avg Response Time: 0.208s


#### B. Query Biaya Formulir/Pendaftaran

- Jumlah Query: 8

- Precision@3: 100.0%

- Recall@3: 100.0%

- Avg Response Time: 0.206s


#### C. Query Syarat Pendaftaran

- Jumlah Query: 1

- Precision@3: 66.7%

- Recall@3: 100.0%

- Avg Response Time: 0.245s


#### D. Query Uang Pangkal

- Jumlah Query: 15

- Precision@3: 100.0%

- Recall@3: 100.0%

- Avg Response Time: 0.241s


### Tabel Hasil Detail - Retrieval

| No | ID | Query | Cat | P@1 | P@3 | P@5 | R@3 | SR | CR | TR | Time |
|:--:|:--:|-------|:---:|:---:|:---:|:---:|:---:|:--:|:--:|:--:|:----:|
| 1 | Q-A01 | Berapa jumlah SMA  | infor | 0% | 0% | 0% | 0% | 0 | 0 | 3 | 0.654 |
| 2 | Q-A02 | Rincian biaya masuk SD Islam Al Azhar 1 ... | biaya | 100% | 100% | 60% | 100% | 3 | 0 | 0 | 0.235 |
| 3 | Q-A03 | Berapa biaya pendidikan TK Islam Al Azha... | biaya | 100% | 100% | 60% | 100% | 3 | 0 | 0 | 0.201 |
| 4 | Q-A04 | Berapa total biaya sekolah | biaya | 100% | 100% | 60% | 100% | 2 | 1 | 0 | 0.206 |
| 5 | Q-A05 | Biaya pendidikan TK Islam Al Azhar 51 Si... | biaya | 100% | 100% | 60% | 100% | 2 | 1 | 0 | 0.212 |
| 6 | Q-A06 | Berapa biaya masuk TK Islam Al Azhar 6 S... | biaya | 100% | 100% | 60% | 100% | 3 | 0 | 0 | 0.207 |
| 7 | Q-A07 | Rincian biaya SMP Islam Al Azhar tahun 2... | biaya | 100% | 100% | 60% | 100% | 1 | 2 | 0 | 0.192 |
| 8 | Q-A08 | Berapa biaya penerimaan murid baru SD Is... | biaya | 100% | 100% | 60% | 100% | 2 | 1 | 0 | 0.182 |
| 9 | Q-A09 | Apa saja komponen biaya sekolah SD Al Az... | biaya | 100% | 100% | 60% | 100% | 2 | 1 | 0 | 0.194 |
| 10 | Q-A10 | Biaya tahunan SD Al Azhar Kebayoran Baru... | biaya | 100% | 100% | 60% | 100% | 2 | 1 | 0 | 0.198 |
| 11 | Q-A11 | Berapa uang sekolah per bulan TK Al Azha... | biaya | 100% | 100% | 60% | 100% | 1 | 2 | 0 | 0.214 |
| 12 | Q-A12 | Biaya pendidikan TK Al Azhar Pasar Mingg... | biaya | 100% | 100% | 60% | 100% | 2 | 1 | 0 | 0.246 |
| 13 | Q-A13 | Apakah biaya TK Al Azhar JAWAB BARAT sud... | biaya | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.234 |
| 14 | Q-A14 | Rincian biaya SMP Al Azhar tahun ajaran ... | biaya | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.189 |
| 15 | Q-A15 | Total  masuk sma Al Azhar padang 32 tahu... | biaya | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.196 |
| 16 | Q-B01 | Berapa biaya formulir pendaftaran SD Al ... | biaya | 100% | 100% | 60% | 100% | 3 | 0 | 0 | 0.242 |
| 17 | Q-B02 | Biaya pendaftaran SD Al Azhar Kebayoran ... | biaya | 100% | 100% | 60% | 100% | 3 | 0 | 0 | 0.195 |
| 18 | Q-B03 | Apakah pendaftaran TK Al Azhar 17 Bintar... | biaya | 100% | 100% | 60% | 100% | 2 | 1 | 0 | 0.205 |
| 19 | Q-B04 | Berapa biaya pendaftaran siswa baru SD A... | biaya | 100% | 100% | 60% | 100% | 2 | 1 | 0 | 0.176 |
| 20 | Q-B05 | Biaya administrasi pendaftaran TK Al Azh... | biaya | 100% | 100% | 60% | 100% | 2 | 1 | 0 | 0.195 |
| 21 | Q-B06 | Apakah formulir pendaftaran Al Azhar gra... | biaya | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.214 |
| 22 | Q-B07 | Berapa biaya daftar ulang SD Al Azhar? | biaya | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.197 |
| 23 | Q-B08 | Biaya pendaftaran online Al Azhar berapa... | biaya | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.222 |
| 24 | Q-B09 | Rincian biaya pendaftaran | rinci | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.226 |
| 25 | Q-C01 | Apa saja dokumen yang dibutuhkan? | syara | 100% | 67% | 40% | 100% | 0 | 2 | 1 | 0.245 |
| 26 | Q-D01 | Berapa uang pangkal SD Al Azhar 27 Cibin... | uang_ | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.388 |
| 27 | Q-D02 | Uang pangkal SD Al Azhar Kebayoran Baru ... | uang_ | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.192 |
| 28 | Q-D03 | Apakah TK Al Azhar 17 Bintaro memiliki u... | uang_ | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.222 |
| 29 | Q-D04 | Berapa uang pangkal masuk TK Al Azhar Pa... | uang_ | 100% | 100% | 60% | 100% | 2 | 1 | 0 | 0.204 |
| 30 | Q-D05 | Uang pangkal SD Al Azhar Bandung berapa? | uang_ | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.207 |
| 31 | Q-D06 | Rincian uang pangkal TK Al Azhar Sidoarj... | uang_ | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.240 |
| 32 | Q-D07 | Apakah uang pangkal bisa dicicil di Al A... | uang_ | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.207 |
| 33 | Q-D08 | Berapa biaya uang gedung SD Al Azhar? | uang_ | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.422 |
| 34 | Q-D09 | Uang pangkal SMP Al Azhar tahun ajaran 2... | uang_ | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.194 |
| 35 | Q-D10 | Apakah uang pangkal berbeda tiap cabang ... | uang_ | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.224 |
| 36 | Q-D11 | Sistem pembayaran uang pangkal Al Azhar ... | uang_ | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.218 |
| 37 | Q-D12 | Uang pangkal TK Al Azhar Sentra Primer b... | uang_ | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.221 |
| 38 | Q-D13 | Apakah uang pangkal sudah termasuk fasil... | uang_ | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.259 |
| 39 | Q-D14 | Biaya awal masuk SD Al Azhar terdiri dar... | uang_ | 100% | 100% | 60% | 100% | 1 | 2 | 0 | 0.216 |
| 40 | Q-D15 | Total uang pangkal dan biaya masuk SD Al... | uang_ | 100% | 100% | 60% | 100% | 0 | 3 | 0 | 0.194 |
| | **AVG** | - | - | **98%** | **97%** | **58%** | **98%** | - | - | - | **0.232** |

**Keterangan:** SR=Sangat Relevan, CR=Cukup Relevan, TR=Tidak Relevan


## Pengujian Response Quality

Sample: 10 queries


### Tabel Hasil Response Quality

| No | ID | Query | R | A | C | Avg | Len | Src | Sim | Time |
|:--:|:--:|-------|:-:|:-:|:-:|:---:|:---:|:---:|:---:|:----:|
| 1 | Q-A01 | Berapa jumlah SMA  | 3 | 3 | 2 | 2.67 | 76 | 3 | 0.74 | 1.235 |
| 2 | Q-A02 | Rincian biaya masuk SD Islam A... | 5 | 5 | 5 | 5.00 | 892 | 3 | 0.86 | 2.789 |
| 3 | Q-A03 | Berapa biaya pendidikan TK Isl... | 5 | 5 | 5 | 5.00 | 551 | 3 | 0.89 | 2.223 |
| 4 | Q-A04 | Berapa total biaya sekolah | 4 | 3 | 2 | 3.00 | 85 | 3 | 0.80 | 1.094 |
| 5 | Q-B01 | Berapa biaya formulir pendafta... | 5 | 5 | 3 | 4.33 | 219 | 3 | 0.89 | 1.292 |
| 6 | Q-B02 | Biaya pendaftaran SD Al Azhar ... | 5 | 5 | 5 | 5.00 | 538 | 3 | 0.86 | 2.061 |
| 7 | Q-C01 | Apa saja dokumen yang dibutuhk... | 3 | 5 | 5 | 4.33 | 909 | 3 | 0.73 | 2.737 |
| 8 | Q-D01 | Berapa uang pangkal SD Al Azha... | 4 | 5 | 4 | 4.33 | 434 | 3 | 0.84 | 12.905 |
| 9 | Q-D02 | Uang pangkal SD Al Azhar Kebay... | 4 | 5 | 3 | 4.00 | 215 | 3 | 0.83 | 1.384 |
| 10 | Q-D03 | Apakah TK Al Azhar 17 Bintaro ... | 4 | 5 | 3 | 4.00 | 221 | 3 | 0.83 | 1.447 |
| | **AVG** | - | **4.20** | **4.60** | **3.70** | **4.17** | - | - | - | **2.917** |

**Keterangan:** R=Relevance, A=Accuracy, C=Completeness, Len=Answer Length, Src=Sources, Sim=Similarity


## Kesimpulan

1. **Retrieval Performance:**

   - Precision@3: 96.7%

   - Recall@3: 97.5%

   - Avg Response Time: 0.232s


2. **Response Quality:**

   - Relevance: 4.20/5

   - Accuracy: 4.60/5

   - Completeness: 3.70/5

   - Overall: 4.17/5


3. **Rekomendasi:** Berdasarkan hasil pengujian, sistem RAG menunjukkan performa baik untuk query informational tentang biaya sekolah.
