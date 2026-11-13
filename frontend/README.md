# 前端 (Vue 3 + Vite)

安裝與執行步驟見根目錄的 [README.md](../README.md)。

```powershell
npm ci          # 安裝套件
npm run dev     # 開發伺服器 http://localhost:5173，/api 轉送到後端 127.0.0.1:8000
npm run build   # 建置到 dist/
```

後端位址不是 `http://127.0.0.1:8000` 時，啟動前設定環境變數 `VITE_BACKEND_URL`。
部署時網站伺服器須把 `/events/:id` 等前端路徑都回傳 `index.html`，否則直接開啟連結或重新整理會得到 404。

## 結構

| 檔案 | 內容 |
|---|---|
| `src/api.js` | 呼叫後端的共用函式：統一錯誤格式、分頁總數、檔案下載；憑證失效時自動清除登入狀態 |
| `src/auth.js` | 登入狀態 (存在 sessionStorage，關閉瀏覽器即失效)、登入、登出、角色 |
| `src/format.js` | 台灣時間顯示與表單轉換、登入後導回的安全檢查、讀取信件連結中的 `#token` |
| `src/eventForm.js` | 建立與修改活動共用的欄位規則 (ER-US-C02、C03) |
| `src/router/index.js` | 路由；依登入、活動管理者、系統管理員限制頁面 (後端仍會再檢查) |
| `src/views/Home.vue` | 首頁：搜尋、篩選、分頁 (ER-US-B01、B04、B05) |
| `src/views/EventDetail.vue` | 活動詳情、報名、取消報名、分享連結與海報 QR (ER-US-B02、B03、B11、D01、D02、E02) |
| `src/views/Login.vue` | 登入、鎖定提示、未驗證時重寄 (ER-US-A04、A07、A03) |
| `src/views/Register.vue` | 註冊與個資同意 (ER-US-A01、A02) |
| `src/views/VerifyEmail.vue` | 信箱驗證 (ER-US-A01、A03) |
| `src/views/ForgotPassword.vue`、`ResetPassword.vue` | 忘記與重設密碼 (ER-US-A08) |
| `src/views/Faq.vue` | 常見問題 (ER-US-B17) |
| `src/views/MyEvents.vue` | 我的活動與歷史紀錄 (ER-US-E01、E02、H03) |
| `src/views/CreateEvent.vue` | 建立活動，未確認主辦規範時先確認 (ER-US-C01、C12、I16) |
| `src/views/ManageEvents.vue` | 單位活動列表、取消活動、下載 QR (ER-US-C15、F07、B11) |
| `src/views/EditEvent.vue` | 修改活動 (ER-US-F01、F02) |
| `src/views/Roster.vue` | 報名名單 (ER-US-G01) |
| `src/views/OrganizerTerms.vue` | 主辦規範 (ER-US-I16) |
| `src/views/Admin.vue` | 系統管理，各分頁在 `src/components/admin/` (ER-US-I01、I02、I05、I06、I12、J02、J03) |
| `src/components/` | 導覽列、活動卡片、活動表單欄位、主辦規範確認、重寄驗證信 |
