# 海大活動報名系統

軟體工程期末專案。前端 Vue 3 + Vite，後端 FastAPI + SQLAlchemy，資料庫 MySQL（本機開發可用 SQLite）。
需求以《軟體需求文件 (SRD)》為準；此分支完成 **MVP** 與 **R2**（前端與後端）。R3 尚未開始。

| 資料夾 | 內容 |
|---|---|
| `backend/` | API、資料模型、初始化腳本、寄信與備份 worker、自動化測試，說明見 [backend/README.md](backend/README.md) 與 [R2 後端交接](backend/docs/R2交接.md) |
| `frontend/` | 網頁介面，說明見 [frontend/README.md](frontend/README.md) |

**R2 有資料表變更，請用全新的測試資料庫，不要直接拿舊 demo.db 啟動，也不要對團隊資料庫執行 `--reset`。**

## 功能範圍

| 版本 | 使用者故事 | 頁面 |
|---|---|---|
| MVP | A04 登入、A05 登出 | `/login`、導覽列「登出」 |
| MVP | B01 瀏覽、B02 詳情、B03 我的報名狀態、B09 聯絡方式 | `/`、`/events/:id` |
| MVP | C01、C02、C03、C12 建立活動 | `/events/new` |
| MVP | D01 報名、D02 登入後回到原頁 | 詳情頁「立即報名」 |
| R2 | A01 註冊、A02 個資同意、A03 重寄驗證信、A07 鎖定提示、A08 重設密碼 | `/register`、`/verify-email`、`/login`、`/forgot-password`、`/reset-password` |
| R2 | B04 關鍵字搜尋、B05 類型與日期篩選、B11 分享連結與海報 QR、B17 常見問題 | `/`、`/events/:id`、`/faq` |
| R2 | E01 我的活動、E02 取消報名、H03 歷史紀錄 | `/me/events`、詳情頁「取消報名」 |
| R2 | C15 單位活動管理、F01 修改活動、F02 異動通知、F07 取消活動、G01 報名名單、I16 主辦規範 | `/manage`、`/manage/events/:id/edit`、`/manage/events/:id/registrations`、`/organizer-terms` |
| R2 | I01、I12 搜尋使用者，I02 指派管理者，I05 活動類型，I06 單位，J02 寄信紀錄，J03 備份 | `/admin` |

## 第一次執行

需要 **Python 3.10 以上** 與 **Node.js 20 以上**。以下指令在 Windows PowerShell 執行，路徑以專案根目錄為起點。

### 1. 安裝後端並建立 .env

```powershell
cd backend
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
```

複製 `.env.example` 為 `.env`，並把 `JWT_SECRET` 換成至少 32 字元的隨機字串。
也可以執行 `.\run.ps1`：它會安裝套件、產生含隨機密鑰的 `.env`，並啟動後端。

### 2. 建立測試資料庫與示範帳號

```powershell
$env:DATABASE_URL = 'sqlite:///./r2-demo.db'
venv\Scripts\python.exe init_data.py --demo
```

- 使用一個**尚不存在**的資料庫檔名；舊的 demo.db 會保留。之後每個終端機都要設定同一個 `DATABASE_URL`。
- `--demo` 會建立示範帳號、示範活動，以及開發用的個資告知、主辦規範、常見問題草案（只能在 `APP_ENV=development` 使用）。
- 不加參數只建立正式的基本資料：系統管理員、單位清單、活動類型。系統管理員密碼取自 `INIT_ADMIN_PASSWORD`；沒有設定時隨機產生並只顯示一次。

示範帳號的密碼都是 `DemoOnly!2026`（只供本機測試，已完成信箱驗證）：

| 帳號 | 角色 | 用途 |
|---|---|---|
| `student1@demo.ntou.edu.tw` | 學生（資工系 1 年級） | 一般報名 |
| `student2@demo.ntou.edu.tw` | 學生（電機系 3 年級） | 已報名「已額滿參訪」 |
| `student3@demo.ntou.edu.tw`、`grad@demo.ntou.edu.tw` | 學生（航管系 4 年級、海生所研究生） | 其他系所與年級 |
| `teacher@demo.ntou.edu.tw`、`staff@demo.ntou.edu.tw` | 教師、行政人員 | 其他身分別 |
| `manager@demo.ntou.edu.tw` | 資工系活動管理者（一個單位） | 活動管理；建立活動時自動帶入主辦單位 |
| `multi@demo.ntou.edu.tw` | 吉他社、學生會的活動管理者（兩個單位） | 活動管理；建立活動時選擇主辦單位 |
| `admin@demo.ntou.edu.tw` | 系統管理員 | `/admin` 系統管理 |

### 3. 啟動後端

```powershell
venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

API 文件：<http://127.0.0.1:8000/docs>

### 4. 啟動寄信與備份 worker（另開一個終端機）

註冊驗證、重設密碼與活動異動通知都會先排入資料庫，再由 worker 寄出。

```powershell
cd backend
$env:DATABASE_URL = 'sqlite:///./r2-demo.db'
venv\Scripts\python.exe worker.py
```

- 沒有設定 SMTP 時，信件不會真的寄出：worker 會重試 3 次後標為「寄送失敗」，可在 `/admin` 的「寄信紀錄」看到並手動重寄。
- 本機測試要拿驗證或重設連結時，可以直接查資料庫的 `outgoing_emails.body`。連結格式是 `http://localhost:5173/verify-email#token=...`。
- SMTP、每日備份（`BACKUP_ENABLED=1`）與還原步驟見 [R2 後端交接](backend/docs/R2交接.md)。

### 5. 啟動前端（再開一個終端機）

```powershell
cd frontend
npm ci
npm run dev
```

開啟 <http://localhost:5173>。前端會把 `/api/*` 轉送到 `http://127.0.0.1:8000`。

## 測試

### 自動化測試（後端）

```powershell
cd backend
venv\Scripts\python.exe -m pytest -q
```

預期結果：`209 passed, 1 skipped`。被略過的是 MySQL 併發測試，要先設定 `MYSQL_TEST_URL` 才會執行（見 backend/README.md）。

- `tests/test_srd_mvp_acceptance.py`：依 SRD 的 MVP 測試方法逐條撰寫，測試名稱帶故事代號。
- `tests/test_r2.py`、`tests/test_my_events.py`、`tests/test_operations.py`：R2 後端功能、個人活動、寄信與備份。
- `tests/test_r2_fixes.py`：整合前端時修正的項目（首頁分頁、異動通知內容、修改錯誤代碼、使用者搜尋顯示管理單位）。

### 效能測試（ER-US-B01、NFR-01-02）

```powershell
cd backend
venv\Scripts\python.exe scripts\load_test_mvp.py
```

自建 1,000 筆活動的暫存資料庫，模擬 50 位使用者同時開首頁與詳情頁，回報 p95 與「3 秒內」比例。
對部署環境量測時加上 `--base-url http://伺服器位址`。只量 API 回應時間，不含瀏覽器繪製。

### 前端建置檢查

```powershell
cd frontend
npm run build
```

### 手動驗收

依上述步驟啟動後端、worker、前端，以示範帳號操作。

**MVP**

1. **瀏覽（B01、B02、B09）**：未登入開啟首頁，看到示範活動依開始時間排序，下方顯示「已顯示 N / 總數」。點進任一活動，不需登入就能看到時間、地點、主辦單位、聯絡方式、報名期間與狀態。
2. **登入後回到原頁（D02）**：未登入時點「登入後報名」，登入後回到原活動頁。
3. **報名（D01、B03）**：點「立即報名」，顯示「報名成功」，按鈕變成「已報名」，人數加 1。
4. **登入鎖定（NFR-05-04、A07）**：同一信箱輸錯密碼 5 次，第 6 次即使密碼正確也顯示「登入失敗次數過多，請於 10 分鐘後再試」。
5. **建立活動（C01、C02、C03、C12）**：以 `multi` 登入，從「活動管理」→「建立活動」。空白送出會標示必填欄位；報名截止晚於活動開始、名額填 0 會被拒絕。

**R2**

6. **註冊（A01、A02）**：`/register` 顯示目前版本的個資告知；不勾選同意、使用非學校信箱都無法註冊；成功後顯示「驗證信已寄到…」。
7. **驗證與重寄（A01、A03）**：驗證前登入顯示「請先完成信箱驗證」並提供「重新寄送驗證信」，60 秒內再寄會顯示剩餘秒數。重寄後舊連結顯示「連結已失效」，新連結驗證成功後可登入。
8. **重設密碼（A08）**：`/forgot-password` 對已註冊與未註冊的信箱都顯示相同訊息；用信中的連結重設後，同一連結再用一次會失效。
9. **搜尋與篩選（B04、B05）**：首頁輸入關鍵字、選類型與日期可組合使用；查無結果時顯示「找不到符合的活動」。
10. **分享（B11）**：詳情頁可複製活動連結；該活動所屬單位的管理者另有「下載海報 QR Code」。
11. **我的活動與取消（E01、E02、H03）**：報名後「我的活動」出現該活動；按「取消報名」會二次確認，取消後名額釋出、詳情頁顯示「已取消」，截止前可再報名。「歷史紀錄」列出已結束的活動，出席狀態為「未記錄」。
12. **活動管理（C15、F01、F02、F07、G01）**：以 `multi` 登入「活動管理」，只看得到吉他社與學生會的活動。修改地點後，報名者會收到列出修改前後內容的信；取消活動需填寫原因並二次確認；「名單」顯示正式報名者。
13. **主辦規範（I16）**：以 `admin` 在「系統管理 → 公告文件」發布新版主辦規範後，管理者再建立活動時會先被要求確認新版本，確認後自動建立。
14. **系統管理（I01、I02、I05、I06、I12）**：`admin` 可依姓名、Email、系所搜尋使用者，並依單位與角色篩選；可指派或取消單位管理者（下次操作即生效），新增、更名、停用單位與活動類型；已被使用的單位與類型無法刪除。
15. **常見問題（B17）**：未登入可從導覽列、登入頁、註冊頁進入 `/faq`；`admin` 發布新版後顯示最新內容與更新時間。
16. **寄信紀錄與備份（J02、J03）**：`/admin` 的「寄信紀錄」可看到重試 3 次仍失敗的信並手動重寄；執行 `worker.py --backup-now` 後「備份」分頁出現成功紀錄。
17. **手機版（NFR-03-01）**：用瀏覽器開發者工具切到 375 px 寬度，所有頁面都能操作，也不會出現水平捲軸。

## 已知限制

- R3（候補、資格、撞期、報到、截止後取消申請等）尚未實作。
- 尚無自動 migration；用全新資料庫測試。團隊既有資料由資料庫負責人安排升級，變更清單見 R2 交接文件。
- 正式 SMTP、MySQL 驗收、HTTPS、部署、跨瀏覽器（NFR-04-01、NFR-05-01）與易用性測試（NFR-03-02）要在部署環境另外進行。
- `init_data.py --demo` 建立的個資告知、主辦規範與常見問題是開發草案，正式上線前須由團隊確認內容後在 `/admin` 發布。
