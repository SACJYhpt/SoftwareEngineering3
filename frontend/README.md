# 前端 (Vue 3 + Vite)

安裝與執行步驟見根目錄的 [README.md](../README.md)。

```powershell
npm ci          # 安裝套件
npm run dev     # 開發伺服器 http://localhost:5173，/api 轉送到後端 127.0.0.1:8000
npm test        # 9 個 API 呼叫與信件連結解析測試
npm run build   # 建置到 dist/
```

後端位址不是 `http://127.0.0.1:8000` 時，啟動前設定環境變數 `VITE_BACKEND_URL`。

## 結構

| 檔案 | 內容 |
|---|---|
| `src/api.js` | 呼叫後端的共用函式，統一處理錯誤格式；憑證失效時自動清除登入狀態 |
| `src/auth.js` | 登入狀態 (存在 sessionStorage，關閉瀏覽器即失效)、登入、登出 |
| `src/format.js` | 台灣時間顯示、表單時間轉換、登入後導回的安全檢查 |
| `src/router/index.js` | 路由；`/events/new` 只開放給活動管理者 |
| `src/views/Home.vue` | 首頁活動列表 (ER-US-B01) |
| `src/views/EventDetail.vue` | 活動詳情與報名 (ER-US-B02、B03、D01、D02) |
| `src/views/Login.vue` | 登入 (ER-US-A04) |
| `src/views/CreateEvent.vue` | 建立活動 (ER-US-C01、C02、C03、C12) |
| `src/components/Navbar.vue` | 導覽列、登出 (ER-US-A05) |
| `src/components/EventCard.vue` | 首頁的活動卡片 |


## 本次新增功能

- `/register`：學校信箱註冊、身分別、系所與學生年級欄位；載入 `/departments` 及目前個資告知，提交明確同意與版本。
- `/verify-email`：透過信件 token 驗證信箱；驗證／重設頁優先接受 `#token=...`，相容 `?token=...`，取出後移除網址上的 token。
- `/forgot-password`、`/reset-password`：忘記密碼與一次性重設。
- 首頁：關鍵字搜尋活動名稱／描述，並可組合活動類型與日期篩選。
- 活動詳情：所有人可複製公開活動連結；單位管理者透過有權限檢查的 `/events/{id}/qr` 下載 PNG，不再使用外部 QR 服務。QR Code 不含登入憑證或個人報到資料。
- 建立活動：若尚未確認最新版主辦規範，先顯示文件，勾選確認後再提交建立。
- 部署使用 Vue Router history 模式時，網站伺服器必須將 `/events/:id` 等前端路徑 fallback 至 `index.html`，否則直接貼上活動網址或重新整理可能得到伺服器 404。

## 與完整 R2 後端的整合界線

帳號流程使用 `/auth/register`、`/auth/verify-email`、`/auth/resend-verification`、`/auth/forgot-password`、`/auth/reset-password`，沒有另一套 password-reset 路徑或記憶體寄信信箱。
新註冊帳號需先驗證；啟動 worker 並設定 SMTP 才會實際寄信，未設定時可先使用根目錄 README 的已驗證示範帳號。

這些是組員已做的部分 R2 畫面。本次沒有新增個人活動／歷史、活動修改／取消、FAQ 管理、使用者／單位／類型管理、寄信與備份管理頁；這些 API 仍保留在後端 `/docs`。
來源、啟動及測試界線見 [整合說明](../docs/前後端整合說明.md)。
