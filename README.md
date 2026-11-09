# 海大活動報名系統

軟體工程期末專案。前端 Vue 3 + Vite，後端 FastAPI + SQLAlchemy，資料庫 MySQL（本機開發可用 SQLite）。
需求以《軟體需求文件 (SRD)》為準；目前完成 **MVP**（R2、R3 尚未開始）。

| 資料夾 | 內容 |
|---|---|
| `backend/` | API、資料模型、初始化腳本與自動化測試，說明見 [backend/README.md](backend/README.md) |
| `frontend/` | 網頁介面，說明見 [frontend/README.md](frontend/README.md) |

## MVP 範圍

| 順序 | 使用者故事 | 頁面 / API |
|---|---|---|
| ① | A04 登入、A05 登出 | `/login`、導覽列「登出」／`POST /auth/login`、`POST /auth/logout` |
| ① | C01、C02、C03、C12 建立活動 | `/events/new`／`POST /events`、`GET /event-types` |
| ② | B01 瀏覽、B02 詳情、B03 我的報名狀態、B09 聯絡方式 | `/`、`/events/:id`／`GET /events`、`GET /events/{id}` |
| ③ | D01 報名、D02 登入後回到原頁 | 詳情頁「立即報名」／`POST /events/{id}/registrations` |
| — | FR-01-12 初始化資料、NFR-05-04 登入鎖定 | `backend/init_data.py`、登入 API |

MVP 不含註冊。帳號、單位、活動類型與管理者授權由 `init_data.py` 建立（見下方步驟 2）。

## 第一次執行

需要 **Python 3.10 以上** 與 **Node.js 20 以上**。以下指令在 Windows PowerShell 執行，路徑以專案根目錄為起點。

### 1. 安裝後端並建立 .env

```powershell
cd backend
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
```

複製 `.env.example` 為 `.env`，並把 `JWT_SECRET` 換成至少 32 字元的隨機字串。
也可以直接執行 `.\run.ps1`：它會自動安裝套件、產生含隨機密鑰的 `.env`，並啟動後端。

### 2. 建立資料庫與測試帳號

```powershell
venv\Scripts\python.exe init_data.py --demo --reset
```

- `--demo`：建立 MVP 驗收用的測試帳號與示範活動（只能在 `APP_ENV=development` 使用）。
- `--reset`：先刪除並重建所有資料表。**資料表結構有變更時必須加**，例如從舊版程式升級上來。
- 不加參數只建立正式的基本資料：系統管理員、單位清單、活動類型。系統管理員的密碼取自 `INIT_ADMIN_PASSWORD`；沒有設定時會隨機產生，並只在畫面上顯示一次。

示範帳號的密碼都是 `DemoOnly!2026`（只供本機測試）：

| 帳號 | 角色 | 用途 |
|---|---|---|
| `student1@demo.ntou.edu.tw` | 學生（資工系 1 年級） | 一般報名 |
| `student2@demo.ntou.edu.tw` | 學生（電機系 3 年級） | 已報名「已額滿參訪」 |
| `student3@demo.ntou.edu.tw`、`grad@demo.ntou.edu.tw` | 學生（航管系 4 年級、海生所研究生） | 其他系所與年級 |
| `teacher@demo.ntou.edu.tw`、`staff@demo.ntou.edu.tw` | 教師、行政人員 | 其他身分別 |
| `manager@demo.ntou.edu.tw` | 資工系活動管理者（一個單位） | 建立活動時自動帶入主辦單位 |
| `multi@demo.ntou.edu.tw` | 吉他社、學生會的活動管理者（兩個單位） | 建立活動時選擇主辦單位 |
| `admin@demo.ntou.edu.tw` | 系統管理員 | MVP 尚無管理功能 |

### 3. 啟動後端

```powershell
venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

API 文件：<http://127.0.0.1:8000/docs>

### 4. 啟動前端（另開一個終端機）

```powershell
cd frontend
npm ci
npm run dev
```

開啟 <http://localhost:5173>。前端會把 `/api/*` 轉送到 `http://127.0.0.1:8000`，所以兩邊都要啟動。

## 測試

### 自動化測試（後端）

```powershell
cd backend
venv\Scripts\python.exe -m pytest -q
```

預期結果：`99 passed, 1 skipped`。被略過的是 MySQL 併發測試，要先設定 `MYSQL_TEST_URL` 才會執行（見 backend/README.md）。

### 前端建置檢查

```powershell
cd frontend
npm run build
```

### 手動驗收（對照 SRD 的 MVP 測試方法）

執行 `init_data.py --demo --reset` 後，依序操作：

1. **瀏覽（B01、B02、B09）**：未登入開啟首頁，看到示範活動依開始時間排序，「不限名額交流會」顯示「0 / 不限」。點進任一活動，詳情頁不需登入就能看到時間、地點、主辦單位、聯絡方式、報名期間與狀態。
2. **登入後回到原頁（D02）**：未登入時在「最後一個名額」點「登入後報名」，會被導到登入頁；以 `student1` 登入後回到原活動頁。
3. **報名（D01、B03）**：點「立即報名」，顯示「報名成功」，按鈕變成「已報名」且不能再按，名額變成 1 / 1、狀態變成「已額滿」。再以 `student3` 登入同一活動，按鈕顯示「名額已滿」。
4. **報名期間**：「報名尚未開始」與「報名已截止」兩個示範活動的按鈕停用，並顯示報名期間。
5. **登出（A05）**：按「登出」後回到首頁、看不到個人資料。後端測試 `test_logout_revokes_token_server_side` 已驗證：登出前的憑證再呼叫 API 會被拒絕。
6. **登入鎖定（NFR-05-04）**：用同一個信箱輸錯密碼 5 次，第 6 次即使密碼正確也顯示「登入失敗次數過多，請於 10 分鐘後再試」。用未註冊的信箱測試，訊息相同。
7. **建立活動（C01、C02、C03、C12）**：以 `multi` 登入，點「建立活動」。
   - 空白送出：每個必填欄位都會被標示。
   - 報名截止晚於活動開始、結束早於開始、名額填 0：都會被拒絕並標示欄位。
   - 填寫正確後送出：跳到新活動的詳情頁，首頁也出現這個活動。
   - 以 `manager` 登入：主辦單位自動帶入「資訊工程學系」。以 `student1` 登入：看不到「建立活動」，直接開 `/events/new` 會被導回首頁。
8. **手機版（NFR-03-01）**：用瀏覽器開發者工具切到 375 px 寬度，所有頁面都能操作，也不會出現水平捲軸。

## 已知限制

- MVP 尚未包含註冊、搜尋、取消報名、候補等 R2／R3 功能。
- 還沒有資料庫 migration：資料表結構變更後，本機請用 `init_data.py --demo --reset` 重建。R2 開始前應導入 Alembic。
- HTTPS、部署、跨瀏覽器驗收（NFR-04-01、NFR-05-01）與易用性測試（NFR-03-02）要在部署環境另外進行。
