# 後端 (FastAPI)

安裝、初始化與執行步驟見根目錄的 [README.md](../README.md)。這份文件說明程式結構、權限規則與 API。

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
| `email_verification_tokens` | 信箱驗證 token 雜湊、期限與使用狀態 |
| `password_reset_tokens` | 密碼重設 token 雜湊、期限與一次性使用狀態 |

目前沒有 migration 工具，`create_all()` 只會建立缺少的資料表，不會修改既有資料表。
資料表結構變更後，開發環境請執行 `init_data.py --demo --reset` 重建；`init_data.py` 偵測到舊結構時會停止並提示。

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
| `POST /auth/register` | 否 | 學校信箱註冊；建立未驗證帳號並寄出 24 小時驗證連結 |
| `GET /units` | 否 | 註冊用系所清單 (department) |
| `POST /auth/verify-email` | 否 | `{ "token" }` 完成信箱驗證 |
| `POST /auth/resend-verification` | 否 | `{ "email" }` 重寄驗證信，同信箱 60 秒冷卻；新連結會撤銷舊連結 |
| `POST /auth/password-reset/request` | 否 | `{ "email" }` 要求寄送重設連結；不揭露信箱是否存在 |
| `POST /auth/password-reset/confirm` | 否 | `{ "token","password" }` 一次性重設密碼；連結 1 小時失效，並撤銷所有既有登入 |
| `POST /auth/login` | 否 | `{ "email","password" }` → `access_token` 與使用者資料；信箱未驗證不可登入 |
| `POST /auth/logout` | 是 | 撤銷目前的憑證，回 204 |
| `GET /auth/me` | 是 | 使用者資料、身分別、系所、年級、`managed_units` |
| `GET /event-types` | 否 | 啟用中的活動類型 |
| `POST /events` | 是，且須管理指定單位 | 建立活動，回 201 |
| `GET /events` | 否 | 尚未開始、未取消的公開活動；支援 `q`、`type`、`date_from`、`date_to` 組合篩選 |
| `GET /events/{id}` | 否 | 活動詳情；帶憑證時多回傳本人的報名狀態 |
| `POST /events/{id}/registrations` | 是 | 報名；新報名回 201，重複送出回 200 與原紀錄 |

### 建立活動的欄位

必填：`unit_id`、`name`、`type` (須為啟用中的活動類型)、`description`、`location`、`contact_information`、`start_time`、`end_time`、`registration_start`、`registration_deadline`。
選填：`capacity` (正整數，省略或 null 表示不限)、`notes`。

- 時間必須帶時區 (例如 `2030-01-12T10:00:00+08:00`)；資料庫以 UTC 儲存，回傳時帶 `Z`。
- 規則：結束晚於開始、報名開始早於報名截止、報名截止不晚於活動開始、活動開始不早於現在。
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
| 422 | `EVENT_START_IN_PAST` | 活動開始早於現在 |
| 422 | `EVENT_TYPE_INVALID` | 活動類型不在清單中或已停用 |
| 409 | `EVENT_CANCELLED`、`EVENT_STARTED` | 活動已取消、已開始 |
| 409 | `REGISTRATION_NOT_OPEN`、`REGISTRATION_CLOSED` | 不在報名期間 |
| 409 | `EVENT_FULL` | 名額已滿 |

### 舊欄位名稱

`EventResponse` 仍同時回傳舊名稱 `category`、`starts_at`、`ends_at`、`registration_opens_at`、`registration_closes_at`、`registered_count`、`waitlist_count` (固定為 0)。
前端已改用新名稱，這些舊欄位可在團隊確認後移除。

## 報名的併發控制

報名在單一交易中先鎖定活動列，再檢查名額並新增紀錄：MySQL 使用 InnoDB `SELECT ... FOR UPDATE`，SQLite 使用 `BEGIN IMMEDIATE`。
`(user_id, event_id)` 唯一限制確保同一人不會重複佔用名額。

## 測試

```powershell
venv\Scripts\python.exe -m pytest -q
```

一般測試使用每次新建的 SQLite 資料庫。MySQL 併發測試需要一個專用的空資料庫 `event_registration_test`：

```powershell
$env:MYSQL_TEST_URL = "mysql+pymysql://event_app:密碼@127.0.0.1:3306/event_registration_test?charset=utf8mb4"
venv\Scripts\python.exe -m pytest -q tests/test_mysql.py
```

`compose.yaml` 可啟動本機 MySQL 8.4 (`docker compose --env-file mysql.env up -d`，密碼範本見 `mysql.env.example`)。


## 註冊、驗證與郵件設定

- 預設允許網域為 `ntou.edu.tw`、`mail.ntou.edu.tw`；可用 `SCHOOL_EMAIL_DOMAINS` 以逗號分隔調整。請依學校實際核發信箱網域確認後再部署。
- 註冊必填姓名、身分別、系所、密碼；學生另須填年級。身分別寫入帳號資料，沒有提供自行修改身分別的 API。
- 密碼至少 8 碼，且包含至少一個英文字母與一個數字。
- 驗證與重設 token 僅以 SHA-256 雜湊存入資料庫；寄出的原始 token 不回傳 API。驗證 token 24 小時有效；重設 token 1 小時有效且只能使用一次。
- 設定 `SMTP_HOST`、`SMTP_PORT`、`SMTP_USER`、`SMTP_PASSWORD`、`SMTP_FROM` 才會透過 SMTP 寄信。未設定 SMTP 時，開發環境會將信件內容放在 `app.state.email_outbox` 並印在後端終端機，方便本機測試；正式環境必須設定郵件服務。
- 設定 `FRONTEND_URL` 為使用者實際可開啟的前端網址，郵件連結才會正確。
- 本次新增 `users.email_verified`、`users.verification_sent_at`、`users.token_version` 及兩張 token 資料表。由於專案目前沒有 migration，既有開發資料庫請先備份，再執行 `python init_data.py --demo --reset` 重建；正式資料庫請先用 migration 加欄位與資料表，勿直接 reset。
