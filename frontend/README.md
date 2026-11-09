# 前端 (Vue 3 + Vite)

安裝與執行步驟見根目錄的 [README.md](../README.md)。

```powershell
npm ci          # 安裝套件
npm run dev     # 開發伺服器 http://localhost:5173，/api 轉送到後端 127.0.0.1:8000
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
