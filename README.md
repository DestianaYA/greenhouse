# Greenhouse IoT Backend

Backend API untuk sistem greenhouse: menerima data sensor, mengirim perintah ke perangkat lewat MQTT, dan melaporkan status sistem.

**Stack:** FastAPI · SQLAlchemy 2 · MySQL · paho-mqtt · Mosquitto · Pydantic · pytest

```
Sensor ──HTTP POST /sensor-data──────────┐
Sensor ──MQTT greenhouse/sensor/{id}────►│ Backend (FastAPI) ──► MySQL
Client ──HTTP POST /device-control──────►│        │
Monitor ─HTTP GET /status───────────────►│        └──MQTT greenhouse/control/{device_id}──► Mosquitto ──► Fan / Vent / Pump
```

Penjelasan arsitektur dan keputusan desain ada di [`docs/DESIGN.md`](docs/DESIGN.md). Presentasi ada di [`docs/presentation.pdf`](docs/presentation.pdf).

---

## 1. Menjalankan dengan Docker Compose (paling mudah)

Prasyarat: Docker dan Docker Compose.

```bash
docker compose up --build
```

Perintah ini menjalankan **MySQL 8**, **Mosquitto**, dan **backend**. Setelah siap:

| URL | Fungsi |
|---|---|
| http://localhost:8000/docs | Swagger UI (coba API langsung dari browser) |
| http://localhost:8000/status | Health check |

Tabel database dibuat otomatis saat backend start.

## 2. Menjalankan secara lokal (tanpa Docker untuk backend)

Prasyarat: Python 3.11+, MySQL (Laragon/XAMPP/native), dan broker Mosquitto.

**a. Siapkan database MySQL**

```sql
CREATE DATABASE greenhouse CHARACTER SET utf8mb4;
CREATE USER 'greenhouse'@'%' IDENTIFIED BY 'greenhouse_pass';
GRANT ALL ON greenhouse.* TO 'greenhouse'@'%';
```

**b. Siapkan broker MQTT** (pilih salah satu)

```bash
# Opsi 1: hanya broker via Docker
docker compose up -d mosquitto

# Opsi 2: Mosquitto terpasang di OS (Linux)
sudo apt install mosquitto mosquitto-clients
# Windows: unduh installer dari https://mosquitto.org/download/
```

**c. Install dan jalankan backend**

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env               # Windows: copy .env.example .env
uvicorn app.main:create_app --factory --reload
```

> Ingin mencoba tanpa MySQL? Ubah `DATABASE_URL=sqlite:///./greenhouse.db` di `.env`.

## 2a. Setup Windows dengan Laragon + Mosquitto (diverifikasi berjalan)

Alur ini sudah diuji end-to-end di Windows tanpa Docker, memakai tools yang lazim dipakai developer Laravel. Kalau `docker pull` lambat/menggantung di jaringanmu (masalah umum di beberapa ISP/kampus/kantor), ini alternatif yang lebih cepat.

**a. MySQL lewat Laragon**

1. Buka Laragon, klik **Start All** (pastikan MySQL menyala)
2. Buka **HeidiSQL** dari Laragon (menu Database), klik **Open** pada koneksi `Laragon.MySQL`
3. Buka tab **Query** (`Ctrl+N` kalau belum ada), jalankan:
   ```sql
   CREATE DATABASE greenhouse CHARACTER SET utf8mb4;
   ```
   (`Ctrl+A` lalu `F9` untuk eksekusi). Tidak perlu buat user baru — pakai `root` bawaan Laragon (password kosong secara default).

**b. Mosquitto native (bukan Docker)**

1. Unduh installer dari [mosquitto.org/download](https://mosquitto.org/download/) → Windows
2. Jalankan installer, biarkan opsi default (termasuk opsi "Service")
3. Installer otomatis mendaftarkan Mosquitto sebagai **Windows Service** dan langsung menjalankannya — tidak perlu dijalankan manual setiap saat. Cek statusnya:
   ```powershell
   Get-Service -Name "mosquitto"
   ```
   Kalau `Status: Running`, broker sudah siap di `localhost:1883` dan otomatis jalan lagi setiap komputer nyala.
4. (Opsional) Supaya perintah `mosquitto_sub` / `mosquitto_pub` bisa dipanggil langsung tanpa path lengkap, tambahkan `C:\Program Files\Mosquitto` ke **Environment Variables → Path** (System variables), lalu buka ulang terminal/VS Code sepenuhnya.

**c. `.env` untuk kombinasi ini**

```
DATABASE_URL=mysql+pymysql://root:@127.0.0.1:3306/greenhouse
MQTT_HOST=localhost
MQTT_PORT=1883
```

**d. Jalankan backend seperti biasa**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env             # lalu sesuaikan seperti di atas
uvicorn app.main:create_app --factory --reload
```

Log startup yang menandakan semua berhasil konek:
```
INFO   [app.database] Database schema is ready
INFO   [app.services.mqtt_service] Connected to MQTT broker
INFO   [app.services.mqtt_service] Subscribed to greenhouse/sensor/+ (qos=1)
INFO   Application startup complete.
```

**e. Verifikasi pesan MQTT tanpa Docker**

```powershell
& "C:\Program Files\Mosquitto\mosquitto_sub.exe" -t "greenhouse/control/#" -v
```
(atau cukup `mosquitto_sub -t "greenhouse/control/#" -v` kalau sudah menambahkan ke PATH di langkah b.4)

Panggil `POST /device-control` dari Swagger UI (`/docs`) di terminal lain — pesannya akan muncul real-time di sini.

## 3. Konfigurasi (`.env`)

| Variabel | Default | Keterangan |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./greenhouse.db` | Contoh MySQL: `mysql+pymysql://user:pass@host:3306/greenhouse` |
| `MQTT_HOST` / `MQTT_PORT` | `localhost` / `1883` | Alamat broker |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | kosong | Isi jika broker memakai autentikasi |
| `MQTT_CONTROL_TOPIC_PREFIX` | `greenhouse/control` | Topic akhir: `{prefix}/{device_id}` |
| `MQTT_CONTROL_QOS` | `1` | QoS perintah kontrol (0, 1, atau 2) |
| `MQTT_CONTROL_RETAIN` | `true` | Perintah terakhir disimpan broker untuk perangkat yang baru online |
| `MQTT_PUBLISH_TIMEOUT` | `3` | Detik menunggu ACK broker sebelum 504 |
| `MQTT_SUBSCRIBE_SENSORS` | `true` | Backend juga menerima data sensor via MQTT |
| `API_KEY` | kosong | Jika diisi, `POST /device-control` wajib header `X-API-Key` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## 4. Contoh pemakaian API

### `POST /sensor-data`: simpan data sensor

```bash
curl -X POST http://localhost:8000/sensor-data \
  -H "Content-Type: application/json" \
  -d '{"sensor_id":"sensor-01","temperature":28.5,"humidity":72.3,"timestamp":"2026-09-21T10:00:00Z"}'
```

Response `201 Created`:

```json
{
  "success": true,
  "message": "Sensor data stored",
  "data": {
    "id": 1, "sensor_id": "sensor-01", "temperature": 28.5, "humidity": 72.3,
    "timestamp": "2026-09-21T10:00:00Z", "received_at": "2026-09-21T10:00:01.123456Z", "source": "http"
  }
}
```

| Field | Tipe | Aturan |
|---|---|---|
| `sensor_id` | string | wajib, 1-64 karakter (`A-Z a-z 0-9 _ -`) |
| `temperature` | number | wajib, -50 sampai 100 (°C) |
| `humidity` | number | wajib, 0 sampai 100 (%) |
| `timestamp` | string ISO 8601 | opsional, default waktu server; tidak boleh di masa depan; disimpan sebagai UTC |

Endpoint tambahan untuk verifikasi: `GET /sensor-data?sensor_id=sensor-01&limit=20`.

### `POST /device-control`: kirim perintah ke perangkat

```bash
curl -X POST http://localhost:8000/device-control \
  -H "Content-Type: application/json" \
  -d '{"device_id":"fan-01","command":"ON"}'
# jika API_KEY diaktifkan, tambahkan:  -H "X-API-Key: <nilai>"
```

Response `202 Accepted`:

```json
{
  "success": true,
  "message": "Command published to MQTT broker",
  "data": {
    "command_id": "90d84241-9233-402d-9c0a-066912fcf48e",
    "device_id": "fan-01", "command": "ON",
    "topic": "greenhouse/control/fan-01", "qos": 1, "retain": true,
    "status": "PUBLISHED", "published_at": "2026-09-21T10:11:34.971277Z"
  }
}
```

`command` hanya `ON` atau `OFF` (huruf kecil otomatis dinormalisasi). Payload yang diterima perangkat di topic `greenhouse/control/fan-01`:

```json
{"command_id": "90d84241-...", "device_id": "fan-01", "command": "ON", "issued_at": "2026-09-21T10:11:34.971277Z"}
```

**Melihat pesan MQTT secara langsung** (buka di terminal terpisah sebelum memanggil API):

```bash
mosquitto_sub -h localhost -t "greenhouse/control/#" -v
```

### `GET /status`: health check

```json
{
  "status": "ok", "service": "ok", "database": "connected", "mqtt": "connected",
  "version": "1.0.0", "uptime_seconds": 42, "timestamp": "2026-09-21T10:00:00Z"
}
```

Mengembalikan **200** jika semua sehat dan **503** dengan `"status": "degraded"` jika database atau MQTT terputus.

### Format error (konsisten di semua endpoint)

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [{"field": "humidity", "message": "Input should be less than or equal to 100"}],
    "request_id": "dbb0b5ab41a0492fb867e5bd779ea86c"
  }
}
```

| HTTP | `code` | Kapan |
|---|---|---|
| 400 | `MALFORMED_JSON` | Body bukan JSON valid |
| 401 | `UNAUTHORIZED` | API key salah/kosong (hanya jika `API_KEY` diset) |
| 404 / 405 | `NOT_FOUND` / `METHOD_NOT_ALLOWED` | Route tidak ada / method salah |
| 422 | `VALIDATION_ERROR` | Field hilang, tipe salah, di luar rentang, command bukan ON/OFF |
| 503 | `MQTT_UNAVAILABLE` | Broker MQTT terputus |
| 503 | `DATABASE_UNAVAILABLE` | Database tidak bisa dijangkau |
| 504 | `MQTT_PUBLISH_TIMEOUT` | Broker tidak mengirim ACK dalam batas waktu |
| 500 | `INTERNAL_ERROR` / `DATABASE_ERROR` | Error tak terduga (detail hanya di log, dengan `request_id`) |

Script demo semua endpoint: `./scripts/demo.sh`.

---

## 5. Mengirim data sensor via MQTT (opsional)

Sensor sungguhan biasanya *publish* ke broker, bukan memanggil HTTP. Backend subscribe ke `greenhouse/sensor/+` dan menyimpan pesan dengan validasi yang sama seperti `POST /sensor-data`. `sensor_id` diambil dari topic.

```bash
mosquitto_pub -h localhost -t greenhouse/sensor/sensor-09 -m '{"temperature":26.4,"humidity":66.0}'

# atau simulasi banyak sensor:
python scripts/simulate_sensors.py --sensors 3 --interval 2
```

Pesan yang tidak valid dibuang dan dicatat di log (tidak menghentikan backend).

## 6. Menjalankan test

```bash
pytest -v
```

66 test, tanpa perlu broker atau MySQL (memakai SQLite sementara dan MQTT tiruan). Cakupan: validasi payload, batas nilai, tipe data, topic injection, normalisasi command, broker mati (503), timeout (504), database mati (503), API key, dan ingestion via MQTT.

## 7. Struktur proyek

```
app/
├── main.py              # app factory, lifespan (start/stop MQTT), exception handlers, middleware
├── config.py            # Settings dari .env (pydantic-settings)
├── database.py          # engine, session, cek koneksi, retry saat startup
├── dependencies.py      # dependency injection (session, service)
├── core/                # exceptions, security (API key), logging, helper waktu
├── routers/             # HTTP layer: sensor.py, device.py, status.py
├── schemas/             # validasi request/response (Pydantic)
├── services/            # logika bisnis: sensor, device, mqtt_service, mqtt_ingestion, status
├── repositories/        # akses database
└── models/              # tabel SQLAlchemy: sensor_readings, device_commands
tests/                   # 66 test
mosquitto/               # konfigurasi broker (dev)
scripts/                 # demo.sh, simulate_sensors.py
docs/                    # DESIGN.md, presentation.pdf
```

### Padanan dengan Laravel

| Laravel | Proyek ini |
|---|---|
| `routes/api.php` + Controller | `app/routers/` |
| Form Request | `app/schemas/` (Pydantic) |
| Eloquent Model | `app/models/` (SQLAlchemy) |
| Service / Repository | `app/services/`, `app/repositories/` |
| `.env` + `config()` | `app/config.py` |
| Service Provider `boot()` | `lifespan` di `app/main.py` |
| Exception Handler | `_register_exception_handlers` di `app/main.py` |
| `php artisan serve` | `uvicorn app.main:create_app --factory --reload` |

## 8. Troubleshooting

| Gejala | Penyebab / solusi |
|---|---|
| `/status` menunjukkan `"mqtt": "disconnected"` | Broker belum jalan atau `MQTT_HOST` salah. Backend akan konek sendiri begitu broker tersedia — tidak perlu restart. |
| `/status` menunjukkan `"database": "disconnected"` | Cek `DATABASE_URL`, user/password, dan MySQL berjalan. Tabel dibuat otomatis begitu DB tersedia, juga tidak perlu restart. |
| `cryptography` error saat konek MySQL 8 | Pastikan `pip install -r requirements.txt` sukses (paket `cryptography` dibutuhkan). |
| Port 1883 / 3306 / 8000 sudah dipakai | Ubah mapping port di `docker-compose.yml` atau hentikan layanan yang bentrok. |
| `docker run` / `docker pull` menggantung tanpa progress | Umum terjadi di jaringan yang membatasi akses ke Docker Hub. Cek dengan `docker pull hello-world`; kalau juga macet, pakai jalur non-Docker di bagian **2a** (Laragon + Mosquitto native) sebagai gantinya. |
| `mosquitto` / `mosquitto_sub` "not recognized" di PowerShell | PATH belum menyertakan `C:\Program Files\Mosquitto`, atau ditambahkan setelah terminal dibuka. Tutup VS Code sepenuhnya lalu buka ulang, atau panggil dengan path lengkap: `& "C:\Program Files\Mosquitto\mosquitto_sub.exe" -v`. |
| Error `Only one usage of each socket address... port 1883` saat menjalankan `mosquitto.exe -v` manual | Installer Windows sudah mendaftarkan Mosquitto sebagai **Service** yang otomatis berjalan. Cek dengan `Get-Service -Name "mosquitto"` — kalau `Running`, broker sudah aktif, tidak perlu dijalankan manual lagi. |
| `Activate.ps1` membuka isi file di editor, bukan menjalankannya | File di-klik langsung di Explorer, bukan dipanggil dari terminal. Ketik `.venv\Scripts\Activate.ps1` di panel **Terminal** VS Code (bukan double-click). |
| `running scripts is disabled on this system` saat aktivasi venv | Jalankan `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`, konfirmasi `Y`, lalu ulangi aktivasi. |

> **Catatan:** seluruh alur di README ini — termasuk skenario database mati (503), broker mati, dan pemulihan otomatis tanpa restart — sudah diverifikasi berjalan nyata di Windows memakai kombinasi Laragon (MySQL) + Mosquitto Windows Service, lewat Swagger UI (`/docs`) dan HeidiSQL.
