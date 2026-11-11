# 後端 (FastAPI)

安裝、初始化與執行步驟見根目錄的 [README.md](../README.md)。這份文件說明程式結構、權限規則與 MVP API；最新版 SRD v2 R2 完整契約及資料庫交接見 [R2交接.md](docs/R2交接.md)。

## 程式結構

| 檔案 | 內容 |
|---|---|
| `main.py` | uvicorn 進入點 (`uvicorn main:app`) |
| `app/api.py` | 路由、登入驗證、登入鎖定、登出 |
| `app/services.py` | 業務邏輯：單位權限、活動狀態、建立活動、報名交易 |
| `app/models.py` | SQLAlchemy 資料表 |
| `app/schemas.py` | Pydantic 請求／回應格式與欄位驗證 |
| `app/security.py` | 密碼雜湊 (Argon2id) 與 JWT |
| `app/config.py` | 讀取 `.env`；相對路徑的 SQLite 一律放在 `backend/` 內 |
| `init_data.py` | 系統初始化 (FR-01-12)：系統管理員、單位、活動類型；`--demo` 另建測試帳號與示範活動 |
| `tests/` | pytest 自動化測試 |
| `app/operations.py` | SMTP 佇列、重試、備份及獨立空資料庫還原 |
| `worker.py` | 常駐寄信與可選的每日備份 worker／明確的還原 CLI |

## 資料表

| 表 | 用途 |
|---|---|
| `users` | 帳號、密碼雜湊、角色 (member／manager／admin)、身分別、系所、年級、啟用狀態 |
| `units` | 單位與類型 (department 系所／office 行政單位／club 社團) |
| `unit_managers` | 使用者是哪些單位的活動管理者；**管理權限只看這張表** |
| `event_types` | 建立活動時可選的活動類型 |
| `events` | 活動；`unit_id` 是歸屬單位，`owner_id` 只記錄建立者 |
| `registrations` | 報名紀錄，同一人對同一活動只有一筆 |
| `revoked_tokens` | 已登出的憑證 (jti)，到期後可清除 |
| `login_throttles` | 每個信箱連續登入失敗次數與鎖定期限 |

目前沒有 migration 工具，`create_all()` 只會建立缺少的資料表，不會修改既有資料表。
R2 請優先使用全新測試資料庫；`init_data.py` 與 API 啟動會偵測舊結構並停止，不自動變更原資料。團隊資料庫升級由資料庫負責人處理，參考 [R2 交接](docs/R2交接.md)。

## 權限規則

- 活動屬於單位。同單位的所有活動管理者都能管理該單位的活動，與建立者是誰無關 (SRD 共通規則、ER-US-C15)。
- `role` 名稱本身不給任何單位權限，連 admin 也一樣；管理權限一律由 `unit_managers` 決定。
- 所有登入使用者 (含管理者) 都能報名活動。
- 權限一律在後端檢查 (`require_manage_unit`)，前端隱藏按鈕只是為了介面一致。

## 登入、登出與鎖定

- 登入成功回傳 JWT (預設 60 分鐘)，每個憑證帶有唯一的 `jti`。
- 登出 (`POST /auth/logout`) 會把該憑證的 `jti` 寫入 `revoked_tokens`，之後用同一個憑證呼叫任何 API 都回 401 `INVALID_TOKEN`。其他裝置的登入不受影響。
- 同一信箱連續失敗 5 次會鎖定 10 分鐘，鎖定期間即使密碼正確也回 429 `LOGIN_LOCKED`。未註冊的信箱也用同樣方式計算，不會透露帳號是否存在。成功登入後歸零。

## API

互動文件：<http://127.0.0.1:8000/docs>

| 方法與路徑 | 登入 | 說明 |
|---|---|---|
| `POST /auth/login` | 否 | `{"email","password"}` → `access_token` 與使用者資料 |
| `POST /auth/logout` | 是 | 撤銷目前的憑證，回 204 |
| `GET /auth/me` | 是 | 使用者資料、身分別、系所、年級、`managed_units` |
| `GET /event-types` | 否 | 啟用中的活動類型 |
| `POST /events` | 是，且須管理指定單位 | 建立活動，回 201 |
| `GET /events` | 否 | 尚未開始、未取消的公開活動，依開始時間排序 |
| `GET /events/{id}` | 否 | 活動詳情；帶憑證時多回傳本人的報名狀態 |
| `POST /events/{id}/registrations` | 是 | 報名；新報名回 201，重複送出回 200 與原紀錄 |
| `GET /me/events` | 是 | 本人正式報名、尚未結束且未取消的活動 |
| `DELETE /events/{id}/registrations/me` | 是 | 截止前取消本人的正式報名，回 200 |

### SRD v2 R2

完整功能、所有新路徑、request body、錯誤及前端配合事項見 [R2交接.md](docs/R2交接.md)。
取消保留 status=cancelled 與 cancelled_at，重新報名重用同筆資料；歷史 API 已提供，R2 出席狀態為「未記錄」。
註冊／主辦規範須確認當前文件版本；驗證信、重設密碼、活動異動／取消通知寫入 outbox，由 worker 寄送及重試。

### 建立活動的欄位

必填：`unit_id`、`name`、`type` (須為啟用中的活動類型)、`description`、`location`、`contact_information`、`start_time`、`end_time`、`registration_start`、`registration_deadline`。
選填：`capacity` (正整數，省略或 null 表示不限)、`notes`。

- 時間必須帶時區 (例如 `2030-01-12T10:00:00+08:00`)；資料庫以 UTC 儲存，回傳時帶 `Z`。
- 規則：結束不早於開始、報名開始不晚於報名截止、報名截止不晚於活動開始、活動開始不早於現在。
- 不接受未宣告的欄位 (例如 `owner_id`)，建立者一律由登入者決定。

### 活動狀態

由 `services.event_status` 依序判斷：已取消 → 已結束 → 進行中 → 報名未開始 → 已截止 → 已額滿 → 開放中。

### 錯誤格式

業務錯誤：`{"detail": {"code": "EVENT_FULL", "message": "名額已滿"}}`。前端依 `code` 判斷，不要比對中文。
欄位格式錯誤：FastAPI 標準的 422，`detail` 是陣列 (含 `loc`、`msg`)。

| HTTP | code | 意義 |
|---|---|---|
| 401 | `AUTH_REQUIRED` | 未登入 |
| 401 | `INVALID_TOKEN` | 憑證過期、無效、已登出或帳號停用 |
| 401 | `INVALID_CREDENTIALS` | 帳號或密碼錯誤 |
| 429 | `LOGIN_LOCKED` | 登入失敗次數過多，`retry_after_minutes` 為剩餘分鐘數 |
| 403 | `UNIT_FORBIDDEN` | 沒有該單位的管理權限 |
| 404 | `UNIT_NOT_FOUND`、`EVENT_NOT_FOUND` | 單位或活動不存在 |
| 404 | `REGISTRATION_NOT_FOUND` | 本人沒有該活動的有效報名，含已取消後重送 |
| 422 | `EVENT_START_IN_PAST` | 活動開始早於現在 |
| 422 | `EVENT_TYPE_INVALID` | 活動類型不在清單中或已停用 |
| 409 | `EVENT_CANCELLED`、`EVENT_STARTED` | 活動已取消、已開始 |
| 409 | `REGISTRATION_NOT_OPEN`、`REGISTRATION_CLOSED` | 不在報名期間 |
| 409 | `EVENT_FULL` | 名額已滿 |

取消 API 也使用 EVENT_CANCELLED、EVENT_STARTED、REGISTRATION_CLOSED；任何失敗都不改變有效報名人數。

### 舊欄位名稱

`EventResponse` 仍同時回傳舊名稱 `category`、`starts_at`、`ends_at`、`registration_opens_at`、`registration_closes_at`、`registered_count`、`waitlist_count` (固定為 0)。
前端已改用新名稱，這些舊欄位可在團隊確認後移除。

## 報名的併發控制

報名在單一交易中先鎖定活動列，再檢查名額並新增紀錄：MySQL 使用 InnoDB `SELECT ... FOR UPDATE`，SQLite 使用 `BEGIN IMMEDIATE`。
`(user_id, event_id)` 唯一限制確保同一人不會重複佔用名額。
取消採用同樣的 event-first 鎖順序，確保釋出的名額不被重複分配。

## 測試

```powershell
venv\Scripts\python.exe -m pytest -q
```

一般測試使用每次新建的 SQLite 資料庫。MySQL 併發測試需要一個專用的空資料庫 `event_registration_test`：

SRD v2 R2 原始結果為 **155 passed, 1 skipped, 1 warning**；2026-11-11 整合組員測試後為 **161 passed, 1 skipped, 1 warning**。外部 SMTP 和正式 MySQL 未驗收，完整界線見 R2 交接及 [前後端整合說明](../docs/前後端整合說明.md)。

R2 測試在 `tests/test_my_events.py`，涵蓋本人隔離、截止邊界、重複取消、重新報名、併發，以及團隊登出撤銷對新 API 的保護。
MySQL 測試另包含取消釋出一席後的併發搶位；未設定 MYSQL_TEST_URL 時仍略過，不能據此宣稱 MySQL 已驗收。

```powershell
$env:MYSQL_TEST_URL = "mysql+pymysql://event_app:密碼@127.0.0.1:3306/event_registration_test?charset=utf8mb4"
venv\Scripts\python.exe -m pytest -q tests/test_mysql.py
```

`compose.yaml` 可啟動本機 MySQL 8.4 (`docker compose --env-file mysql.env up -d`，密碼範本見 `mysql.env.example`)。
