# Penjelasan Desain

Dokumen ini menjelaskan tiga hal yang diminta assignment: **arsitektur sistem**, **integrasi MQTT**, serta **penanganan error dan edge case**. Bagian akhir berisi trade-off dan keterbatasan yang disengaja.

## 1. Arsitektur sistem

### Gambaran alur data

```
                        ┌───────────────────────────────────────────┐
 Sensor ── HTTP ───────►│  routers ─► services ─► repositories ──────┼──► MySQL
 Sensor ── MQTT ───────►│               ▲                            │
   (greenhouse/sensor/+)│               │                            │
 Client ── HTTP ───────►│  routers ─► DeviceService ─► MqttService ──┼──► Mosquitto ──► Fan / Vent / Pump
 Monitor ─ HTTP ───────►│  routers ─► StatusService (cek DB + MQTT)  │      (greenhouse/control/{device_id})
                        └───────────────────────────────────────────┘
                                     FastAPI + paho-mqtt
```

### Pola: layered architecture

| Layer | Folder | Tanggung jawab | Tidak boleh |
|---|---|---|---|
| Router | `routers/` | HTTP saja: menerima request, memanggil service, membentuk response | Berisi logika bisnis atau query |
| Schema | `schemas/` | Kontrak data dan validasi (Pydantic) | Mengakses DB/MQTT |
| Service | `services/` | Logika bisnis: bentuk topic, publish, audit, aturan ingestion | Tahu soal HTTP |
| Repository | `repositories/` | Query database | Berisi aturan bisnis |
| Model | `models/` | Definisi tabel | - |

**Alasan:** setiap layer bisa diuji dan diganti sendiri. Contoh nyata di proyek ini: `SensorService` dipakai oleh dua "pintu masuk", yaitu HTTP (`POST /sensor-data`) dan MQTT (`SensorMqttIngestor`). Validasi dan penyimpanannya identik karena tidak ada logika yang tertanam di router. Dependency injection (`Depends`) merangkai semuanya, dan `create_app(settings, mqtt_service)` menerima dependency dari luar sehingga test cukup mengganti broker asli dengan `FakeMqtt`.

### Sync vs async

Endpoint ditulis dengan `def` biasa (bukan `async def`). FastAPI menjalankannya di threadpool, sehingga query SQLAlchemy dan `publish` paho yang bersifat blocking tidak menghentikan event loop. Ini lebih aman daripada `async def` yang memanggil library blocking. Kalau nanti beban meningkat, bagian ini bisa dimigrasikan ke `asyncpg`/`aiomysql` dan `aiomqtt` tanpa mengubah layer lain.

### Database

- Dua tabel: `sensor_readings` (data sensor) dan `device_commands` (audit setiap perintah kontrol, statusnya `PUBLISHED` atau `FAILED`).
- Semua waktu disimpan sebagai **UTC**. Input dengan offset (misalnya `+07:00`) dikonversi, input tanpa zona dianggap UTC. Response selalu berakhiran `Z`.
- Index gabungan `(sensor_id, timestamp)` untuk query "data terbaru per sensor".
- Tabel dibuat otomatis saat startup (`create_all`) agar penguji cukup menjalankan satu perintah. Untuk produksi, gunakan migrasi Alembic (lihat bagian 5).

## 2. Integrasi MQTT

### Koneksi

`MqttService` membungkus `paho-mqtt` 2.x:

- `connect_async()` + `loop_start()`: koneksi berjalan di thread jaringan paho, sehingga tidak memblokir FastAPI. Backend **tetap bisa start walau broker belum menyala**.
- `reconnect_delay_set(1, 30)`: reconnect otomatis dengan exponential backoff (1 detik sampai 30 detik).
- Semua subscription didaftarkan ulang di `on_connect`, jadi setelah broker restart, ingestion sensor pulih sendiri. Ini sudah diuji dengan mematikan dan menyalakan Mosquitto sungguhan.
- `client_id` diberi sufiks acak agar dua instance backend tidak saling menendang dari broker.

### Struktur topic

| Topic | Arah | Isi |
|---|---|---|
| `greenhouse/control/{device_id}` | Backend → perangkat | Perintah ON/OFF |
| `greenhouse/sensor/{sensor_id}` | Sensor → backend | Data pengukuran (opsional, alternatif HTTP) |
| `greenhouse/backend/status` | Backend → siapa saja | `online` / `offline` (retained + Last Will) |

Payload perintah berupa JSON, bukan string `ON` polos, agar bisa diperluas dan dilacak:

```json
{"command_id": "uuid", "device_id": "fan-01", "command": "ON", "issued_at": "2026-09-21T10:11:34Z"}
```

`command_id` sama dengan yang tersimpan di tabel audit dan yang dikembalikan ke client, sehingga satu perintah bisa ditelusuri dari API sampai ke perangkat.

### Pilihan QoS dan retain

| Pengaturan | Nilai | Alasan |
|---|---|---|
| QoS | **1** (at-least-once) | Perintah tidak boleh hilang. QoS 0 bisa hilang tanpa jejak, QoS 2 terlalu berat untuk perintah yang sudah idempoten. Backend menunggu PUBACK dari broker, jadi "sukses" berarti broker benar-benar menerima. |
| Retain | **true** | Broker menyimpan perintah terakhir per perangkat. Kipas yang baru menyala atau reconnect langsung mengetahui status yang diinginkan. Diuji: subscriber yang datang belakangan langsung menerima `ON` terakhir. Bisa dimatikan lewat `MQTT_CONTROL_RETAIN=false`. |
| Last Will | `offline` | Jika backend mati mendadak, broker yang mengumumkan `offline`. Saat shutdown normal, backend mengirim `offline` sendiri (diuji dengan SIGTERM). |

### Keputusan penting: *fail fast*, bukan antre offline

Jika broker terputus, `POST /device-control` langsung menjawab **503**, dan perintah tidak diantrekan oleh library. Alasannya: "nyalakan pompa" yang tertahan lalu terkirim satu jam kemudian bisa membahayakan tanaman. Client yang tahu perintahnya gagal bisa memutuskan sendiri untuk mencoba lagi.

### Kenapa 202 Accepted, bukan 200

Balasan sukses `202` karena PUBACK hanya membuktikan **broker** menerima pesan, bukan bahwa **perangkat** sudah menjalankannya. Eksekusi di perangkat bersifat asinkron. Ini sifat dasar sistem event-driven, dan status HTTP mencerminkannya. (Konfirmasi dari perangkat bisa ditambahkan lewat topic `greenhouse/ack/{device_id}`, lihat bagian 5.)

## 3. Penanganan error dan edge case

### Prinsip

1. **Format error tunggal.** Semua error memakai `{"success": false, "error": {"code", "message", "details", "request_id"}}`. `code` stabil untuk mesin, `message` untuk manusia.
2. **Status HTTP bermakna.** 4xx = kesalahan client, 5xx = masalah server/dependency. 503 = dependency (DB/MQTT) sedang mati dan aman untuk dicoba ulang.
3. **Tidak membocorkan internal.** Stack trace dan pesan driver hanya masuk log. Client menerima pesan generik plus `request_id` (juga dikirim sebagai header `X-Request-ID`) untuk dicocokkan dengan log.
4. **Gagal sebagian, bukan gagal total.** Aplikasi tetap hidup ketika DB atau MQTT mati.

### Tabel edge case

| Situasi | Perilaku |
|---|---|
| Body bukan JSON valid | 400 `MALFORMED_JSON` |
| Body kosong / field wajib hilang | 422, `details[].field` menunjuk field yang bermasalah |
| `"temperature": "28.5"` (string), `true`, `null` | 422. Validasi tipe **strict**, tidak ada koersi diam-diam. |
| `NaN` / `Infinity` | Ditolak (`allow_inf_nan=False`) |
| Kelembapan > 100, suhu 150 °C | 422 (rentang wajar sensor) |
| `timestamp` di masa depan (> 5 menit) | 422. Toleransi 5 menit untuk selisih jam perangkat. |
| `timestamp` dengan zona waktu berbeda | Dikonversi ke UTC |
| Field tambahan di payload sensor (misal `battery`) | Diabaikan agar firmware baru tidak merusak ingestion |
| `command` = `on`, ` Off ` | Dinormalisasi ke `ON`/`OFF` |
| `command` = `TOGGLE`, `1`, `true`, kosong | 422 |
| `device_id` berisi `/`, `#`, `+`, spasi, atau > 64 karakter | 422. Whitelist karakter mencegah **topic injection**, misalnya `#` yang bisa menarget banyak perangkat atau `x/../y` yang keluar dari namespace. |
| Broker MQTT mati saat `/device-control` | 503 `MQTT_UNAVAILABLE`, tercatat `FAILED` di audit |
| Broker tidak mengirim ACK dalam `MQTT_PUBLISH_TIMEOUT` | 504 `MQTT_PUBLISH_TIMEOUT` |
| Database mati saat `/sensor-data` | 503 `DATABASE_UNAVAILABLE` (bukan 500, bukan crash) |
| Database mati saat `/device-control` | Publish **tetap berhasil**. Audit adalah best-effort, kegagalannya hanya dicatat di log. Kegagalan pencatatan tidak boleh menggagalkan perintah yang sudah terkirim. |
| Database belum siap saat backend start | Retry (`DB_STARTUP_RETRIES`), lalu start dalam mode *degraded*. `/status` melaporkan `disconnected`, dan tabel dibuat otomatis begitu DB pulih. |
| Broker belum siap saat backend start | Backend start normal, koneksi diulang otomatis di background |
| Pesan MQTT sensor bukan JSON / tidak valid | Dibuang + di-log warning. Exception di handler **tidak boleh** lolos ke thread paho karena akan mematikan loop MQTT. |
| Pesan MQTT berisi `sensor_id` palsu di payload | Diabaikan. `sensor_id` diambil dari topic. |
| API key salah/kosong (jika `API_KEY` diset) | 401. Perbandingan `secrets.compare_digest` (tahan timing attack). |
| Route tidak ada / method salah | 404 / 405 dalam format error yang sama |
| Exception tak terduga | 500 generik + `request_id`, detail lengkap di log |
| Shutdown (SIGTERM) | `lifespan` mengirim `offline`, disconnect MQTT bersih, dan menutup pool DB |

### `/status` dan monitoring

`GET /status` memeriksa database (`SELECT 1`) dan `is_connected` pada client MQTT, lalu mengembalikan **200** jika semuanya sehat dan **503** jika ada yang mati. Load balancer atau uptime monitor cukup membaca status code. Bentuk response `/status` sengaja datar (tanpa envelope `success/data`) karena konvensi tooling monitoring.

## 4. Ringkasan keputusan desain dan trade-off

| Keputusan | Pilihan | Alternatif | Trade-off |
|---|---|---|---|
| Framework | FastAPI | Express / Laravel | Validasi + Swagger otomatis dan tipe eksplisit. Ekosistemnya baru bagi developer Laravel. |
| Database | MySQL via SQLAlchemy | PostgreSQL / SQLite | Sesuai keahlian tim. SQLAlchemy membuat ganti DB cukup dengan `DATABASE_URL` (SQLite dipakai di test). |
| Ingestion | HTTP **dan** MQTT memakai satu service | HTTP saja | Sedikit lebih banyak kode, tetapi mencerminkan alur nyata IoT → MQTT → Backend → DB. |
| Perintah kontrol | Fail fast + QoS 1 + audit | Antrean persisten | Sederhana dan aman. Tidak ada retry otomatis, jadi client yang memutuskan. |
| Validasi | Strict + whitelist ID | Koersi longgar | Menolak lebih banyak input, tetapi data di DB bersih dan topic aman. |
| Migrasi skema | `create_all` saat startup | Alembic | Cukup untuk demo. Produksi butuh migrasi berversi. |

## 5. Keterbatasan dan pengembangan lanjutan

Bagian ini sengaja dituliskan agar jelas mana yang sudah dipertimbangkan tetapi belum dikerjakan.

- **Timeout bukan berarti pasti gagal.** Jika PUBACK terlambat, backend membalas 504 padahal paket mungkin sampai ke broker. Karena ON/OFF bersifat idempoten, dampaknya kecil (semantik at-least-once), tetapi client sebaiknya tidak menganggap 504 sebagai "pasti tidak terkirim".
- **Belum ada konfirmasi dari perangkat.** Pola berikutnya: perangkat mem-publish ke `greenhouse/ack/{device_id}` dengan `command_id`, dan backend memperbarui status audit menjadi `ACKED`.
- **Migrasi database:** ganti `create_all` dengan Alembic.
- **Keamanan broker:** konfigurasi Mosquitto di repo ini hanya untuk pengembangan (anonymous, tanpa TLS). Produksi memerlukan `password_file`, ACL per perangkat, dan TLS (port 8883). Backend sudah mendukung `MQTT_USERNAME`/`MQTT_PASSWORD`.
- **Skala besar:** bila volume sensor tinggi, ingestion MQTT sebaiknya memakai antrean batch insert atau time-series DB (TimescaleDB/InfluxDB). Untuk skala assignment ini, insert per pesan sudah memadai.
- **Rate limiting** pada `/device-control` dan autentikasi per-user (JWT) belum ada. Saat ini hanya API key statis opsional.
- **Beberapa instance backend:** semuanya akan subscribe ke `greenhouse/sensor/+` dan menyimpan data ganda. Solusinya *shared subscription* MQTT 5 (`$share/...`).
