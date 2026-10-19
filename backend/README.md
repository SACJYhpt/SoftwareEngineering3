# FastAPI MVP ①／②／③ 後端

本次依最新版《軟體需求文件(SRD).md》及使用者確認的範圍完成：登入、建立活動、瀏覽活動、本人報名狀態與基本報名。
沿用既有 FastAPI、SQLAlchemy、登入與報名交易，沒有新增第二套架構。

## 範圍與暫定假設

- 活動歸屬 `unit_id`，同單位的被授權管理者皆可管理；一人可管理多個單位。
- `owner_id` 保留原欄位名稱，僅記錄建立者；由後端設定，不能作為管理權限依據。
- member／manager／admin 均保有一般報名能力。管理單位的資格只由 `unit_managers` 決定。
- 不額外給 admin 自動管理所有單位的特權；建立活動也需指定單位的授權。
- 上述角色與歸屬假設仍以 `PROVISIONAL` 註記，待團隊最終確認。
- 登入失敗鎖定 5 次／10 分鐘，因 SRD 優先級矛盾依使用者指示暫不實作。
- 未實作任何 R2／R3／R4 或未排定功能：註冊、登出、單位 CRUD、候補、取消、資格、衝突、Email、草稿、圖片、報到、地圖與日曆等均不在本次。

## 執行與資料庫

本機 Python 虛擬環境位於 `backend/venv`，依賴清單沿用 `requirements.txt`；測試依賴為 `requirements-dev.txt`。
在 backend 工作目錄執行 `venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000`。
互動文件：<http://127.0.0.1:8000/docs>；OpenAPI：<http://127.0.0.1:8000/openapi.json>。

本次沒有 migration。舊 demo.db 缺少 unit_id／contact_information，時間限制也不同，**不能直接使用**。
`create_all()`、`init_db.py` 只會建立缺少的資料表，不會更新舊表。未更動、刪除或重建舊 demo.db。
應使用符合當前模型的全新測試資料庫；團隊 MySQL 依既有設定連線，不新增 Docker 或部署架構。
首次設定仍可參考 `.env.example` 和 `run.ps1`，必須設定至少 32 字元隨機 JWT_SECRET。
`seed_demo.py` 只在 development 建立示範使用者、單位、授權、活動與一筆滿額示範報名，不是正式帳號管理或遷移工具。
既有 seed 重跑不刪資料、不重設日期，demo 活動可能隨時間到期。

## 資料表

| 表 | 目的 |
|---|---|
| users | 既有帳號、密碼雜湊、角色名稱、啟用狀態 |
| units | 單位 id、name |
| unit_managers | 使用者與管理單位的關聯，user_id＋unit_id 為組合主鍵 |
| events | unit_id 為歸屬，owner_id 為建立者，活動資訊與 contact_information |
| registrations | user_id、event_id、registered_at，同人同活動唯一 |

未新增候補、取消或出席等未來狀態資料表。
資料庫仍保留原欄位 `category / starts_at / ends_at / registration_opens_at / registration_closes_at`，由 API 映射新命名。

## API 契約

### 1. POST /auth/login

```json
{"email":"manager@demo.ntou.edu.tw","password":"DemoOnly!2026"}
```

成功 200：

```json
{
  "access_token":"登入憑證",
  "token_type":"bearer",
  "expires_in":3600,
  "user":{
    "id":3,"email":"manager@demo.ntou.edu.tw","name":"示範活動管理者","role":"manager",
    "managed_units":[{"id":1,"name":"活動主辦單位"}]
  }
}
```

帳密錯誤與停用帳號統一回 401 INVALID_CREDENTIALS，不透露錯誤的是帳號或密碼。
密碼仍為 Argon2id 加鹽雜湊，token 預設 60 分鐘。示範帳密僅供本機假資料；沒有新增註冊或登出。

### 2. GET /auth/me

帶 `Authorization: Bearer <access_token>`，回 200 與上述 user 物件相同結構。
`managed_units` 供建立活動時選擇自己的管理單位，不是單位 CRUD，也不依角色名稱猜測授權。
資格可能隨授權變更，因此建立 API 每次仍重新檢查。無單位授權者得到空清單。

### 3. POST /events

需登入且具有指定 unit_id 的授權；成功 201，回傳完整 EventResponse。
請依實際測試時間調整下列日期，不能照固定範例日期假定目前開放報名。

```json
{
  "name":"Python 入門講座",
  "type":"講座",
  "description":"活動內容說明",
  "start_time":"2030-01-12T10:00:00+08:00",
  "end_time":"2030-01-12T12:00:00+08:00",
  "location":"海大資訊工程學系",
  "registration_start":"2030-01-01T09:00:00+08:00",
  "registration_deadline":"2030-01-11T17:00:00+08:00",
  "capacity":20,
  "unit_id":1,
  "contact_information":"活動窗口：events@example.edu.tw",
  "notes":"選填注意事項"
}
```

- 除 capacity、notes 外，上述欄位皆必填。capacity 省略或 null 表示不限。
- 必填文字先去除頭尾空白，不能為空；type 暫為非空文字，不提前建立 R2 類型維護功能。
- capacity 必須是真正的正整數；字串、布林、小數、0、負數都拒絕。unit_id 為正整數。
- 時間必須帶 Z 或 UTC offset；儲存為 UTC，回傳帶 Z。避免前後端對無時區時間各自解讀。
- end_time > start_time；registration_start < registration_deadline；registration_deadline <= start_time。
- start_time 不得早於後端現在時間，剛好現在允許。
- owner_id 由登入使用者決定；傳入 owner_id 或其他未宣告欄位會回 422，不會讓前端指定建立者。
- 找不到單位回 404 UNIT_NOT_FOUND，未授權回 403 UNIT_FORBIDDEN。

### 4. GET /events

訪客可讀，回 200 的 EventResponse 陣列。
只包含公開、未取消且尚未開始的活動，依開始時間、id 排序。不加搜尋、篩選或分頁等額外功能。
可帶登入憑證取得本人報名狀態；憑證失效時回 401，前端應清除失效憑證後重新登入或以訪客查詢。

### 5. GET /events/{event_id}

訪客可讀公開活動，包含已取消、進行中、已結束的公開活動；不存在或非公開回 404 EVENT_NOT_FOUND。
EventResponse 的主要欄位如下：

```json
{
  "id":1,
  "name":"Python 入門講座",
  "type":"講座",
  "description":"活動內容說明",
  "location":"海大資訊工程學系",
  "notes":null,
  "unit_id":1,
  "unit":{"id":1,"name":"活動主辦單位"},
  "contact_information":"活動窗口：events@example.edu.tw",
  "start_time":"2030-01-12T02:00:00Z",
  "end_time":"2030-01-12T04:00:00Z",
  "registration_start":"2030-01-01T01:00:00Z",
  "registration_deadline":"2030-01-11T09:00:00Z",
  "registration_count":0,
  "capacity":20,
  "status":"開放中",
  "my_registration_status":null,
  "can_register":false
}
```

上例 status 僅示意其格式，實際狀態由請求當下時間計算。
unit 即主辦單位；contact_information 是活動聯絡資訊，沒有多建一套 organizer 資料表。
訪客 `my_registration_status=null`，不查詢私人報名紀錄；已登入者為「未報名」或「已報名」。
`can_register` 供前端提示，最終仍由報名 API 重新檢查。

狀態集中於 `services.event_status`，優先順序為：

1. 已取消。
2. 現在 >= 結束：已結束。
3. 現在 >= 開始：進行中。
4. 現在 < 報名開始：報名未開始。
5. 現在 >= 報名截止：已截止。
6. 有限額且正式人數 >= 名額：已額滿。
7. 其餘：開放中。

為降低既有接口變更，同時保留 category、starts_at、ends_at、registration_opens_at、registration_closes_at、registered_count 舊回傳名稱，值分別等同新欄位。
新整合請優先使用上例的新名稱，團隊確認後再決定是否移除舊別名。
`waitlist_count=0` 仍為舊相容欄位，MVP 沒有實作候補，不可視為真正候補查詢。

### 6. POST /events/{event_id}/registrations

需登入，沒有 request body；不要傳入 user_id 或 owner_id 指定報名者。
member／manager／admin 都可報名，不受管理單位限制。
新報名成功 201，回應：

```json
{
  "registration_id":1,
  "event_id":1,
  "status":"registered",
  "registered_at":"2030-01-10T00:00:00Z",
  "registration_count":1,
  "capacity":20,
  "already_registered":false,
  "message":"報名成功",
  "registration_status":"已報名",
  "registered_count":1
}
```

重複送出回 200、already_registered=true、相同 registration_id，人數不增加。
已報名後的重送，即使期間已結束，也只回原紀錄，不新增名額。
新報名只接受 `registration_start <= 現在 < registration_deadline`；已開始、已取消亦拒絕。
capacity=null 不限名額；有限額時先鎖活動列，再檢查人數並新增，交易成功才提交。
保留 `(user_id,event_id)` 唯一限制；失敗會 rollback，不改變正式人數。
MySQL 使用 InnoDB `FOR UPDATE`，SQLite 測試使用 `BEGIN IMMEDIATE`，不能把 SQLite 結果當成 MySQL 驗收。

## 錯誤契約

業務錯誤不需要解析中文，以 HTTP status 與 detail.code 判斷：

```json
{"detail":{"code":"EVENT_FULL","message":"名額已滿"}}
```

| HTTP | detail.code | 意義 |
|---|---|---|
| 401 | AUTH_REQUIRED | 未登入 |
| 401 | INVALID_TOKEN | 憑證過期、無效或帳號失效 |
| 401 | INVALID_CREDENTIALS | 登入帳密錯誤或帳號停用 |
| 403 | UNIT_FORBIDDEN | 沒有指定單位管理資格 |
| 404 | UNIT_NOT_FOUND | 單位不存在 |
| 404 | EVENT_NOT_FOUND | 活動不存在或非公開 |
| 422 | EVENT_START_IN_PAST | 活動開始早於現在 |
| 409 | EVENT_CANCELLED | 活動已取消 |
| 409 | EVENT_STARTED | 活動已開始或結束，不接受新報名 |
| 409 | REGISTRATION_NOT_OPEN | 報名未開始 |
| 409 | REGISTRATION_CLOSED | 報名已截止 |
| 409 | EVENT_FULL | 名額已滿 |

Pydantic 格式／必填／時間順序錯誤維持 FastAPI 標準 **422 detail 陣列**，使用 loc、type、msg 處理。
因此整合端須區分 detail 為物件（業務錯誤）或陣列（輸入驗證）；沒有建立自訂錯誤框架。
這次將先前 detail 純字串改為結構化物件，舊示範客戶端的錯誤顯示需配合調整，本次沒有改前端。

## 單位授權共用入口

`can_manage_unit(db,user_id,unit_id)` 判斷啟用中的使用者是否有授權。
`require_manage_unit(...)` 重用前者並回 403，POST /events 已呼叫它；不依 owner_id 或 role 名稱放行。
前端從登入結果或 GET /auth/me 的 managed_units 選擇單位，但伺服器仍會再次驗證。

## D02 登入後返回

登入後導回原頁主要由前端處理，若未來後端接收 return URL，必須限制為系統內部路徑。
目前沒有接收 return URL，也沒有為此新增 API 或重新導向功能。

## 測試與驗收界線

在 backend 執行 `venv\Scripts\python.exe -m pytest -q`。
一般測試以獨立 SQLite 資料庫執行，包含建立／瀏覽／報名的 API 串接、欄位驗證、授權、狀態邊界、重複與併發報名。
本次結果：**86 passed, 1 skipped**。跳過的是需 MYSQL_TEST_URL 的 MySQL 併發測試；尚未做正式 MySQL 完整驗收。
原有 Starlette/httpx 測試轉接器有一則淘汰警告，沒有因此修改依賴或擴充功能。

MySQL 測試只接受名為 event_registration_test、符合新模型的專用測試資料庫。
設定 MYSQL_TEST_URL 後執行 `venv\Scripts\python.exe -m pytest -q tests/test_mysql.py`；該測試建立自己的資料並於結束清理。
現有千次報名測試以 32 workers 送出服務呼叫，另有 HTTP 搶最後一席；不等於千條同時 HTTP 連線或 3 秒效能驗收。

HTTPS、部署、跨瀏覽器、正式負載／易用性與前端 D02 驗收未在本次範圍。
SRD 的單位歸屬、角色兼任及時間嚴格順序採使用者此次明確指定；其餘文件內部矛盾留待團隊同步。
沒有修改 Vue、刪除既有檔案、commit 或 push。
