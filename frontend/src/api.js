// Thin wrapper around fetch for the FastAPI backend.
// Business errors arrive as {detail: {code, message, ...}}; validation errors as {detail: [{loc, msg}]}.
import { auth, clearSession } from './auth'

const BASE = import.meta.env.VITE_API_BASE || '/api'

export class ApiError extends Error {
  constructor(status, code, message, fieldErrors = {}, detail = {}) {
    super(message)
    this.status = status
    this.code = code
    this.fieldErrors = fieldErrors
    // Extra fields of a business error, e.g. retry_after_seconds.
    this.detail = detail
  }
}

// English validator messages from the backend, shown in Chinese.
const VALIDATION_MESSAGES = [
  ['end_time must be later than start_time', 'end_time', '結束時間必須晚於開始時間'],
  ['registration_start must be earlier than registration_deadline', 'registration_start', '報名開始必須早於報名截止'],
  ['registration_deadline must not be later than start_time', 'registration_deadline', '報名截止不可晚於活動開始'],
  ['password must contain letters and digits', 'password', '密碼至少 8 碼，且須同時包含英文字母與數字'],
  ['invalid email', 'email', '信箱格式不正確'],
  ['name and student grade are required', 'grade', '請填寫姓名；學生須選擇年級'],
  ['reason cannot be blank', 'reason', '請填寫原因'],
]

function toApiError(status, body) {
  const detail = body && body.detail
  if (detail && !Array.isArray(detail) && typeof detail === 'object') {
    return new ApiError(status, detail.code, detail.message || '發生錯誤', {}, detail)
  }
  if (Array.isArray(detail)) {
    const fieldErrors = {}
    for (const item of detail) {
      const known = VALIDATION_MESSAGES.find(([text]) => String(item.msg).includes(text))
      const field = known ? known[1] : item.loc && item.loc[1]
      fieldErrors[field || '_form'] = known ? known[2] : '此欄位格式不正確'
    }
    const first = Object.values(fieldErrors)[0]
    return new ApiError(status, 'VALIDATION_ERROR', first || '輸入資料有誤，請檢查標示的欄位', fieldErrors)
  }
  return new ApiError(status, 'HTTP_' + status, status >= 500 ? '伺服器發生錯誤，請稍後再試' : '發生錯誤')
}

async function send(path, { method = 'GET', body, withAuth = true }) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (withAuth && auth.token) headers.Authorization = 'Bearer ' + auth.token
  try {
    return await fetch(BASE + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  } catch {
    throw new ApiError(0, 'NETWORK_ERROR', '無法連線到伺服器，請確認網路或後端是否啟動')
  }
}

// Throws the API error; an expired or revoked login is cleared first. Returns only when the
// caller marked the read as public (guestRetry), so it can be repeated as a guest.
async function failure(response, options) {
  const error = toApiError(response.status, await response.json().catch(() => null))
  if (error.code === 'INVALID_TOKEN') {
    clearSession()
    if (options.guestRetry && (options.method || 'GET') === 'GET' && options.withAuth !== false) return
  }
  throw error
}

// withTotal: resolve to {data, total}, total from the X-Total-Count header of paged lists.
// guestRetry: a public read (home list, event detail) that should still show as a guest when
// the login has expired. Private reads are not retried, so the page says 「登入已失效」.
export async function request(path, options = {}) {
  const response = await send(path, options)
  if (!response.ok) {
    await failure(response, options)
    return request(path, { ...options, withAuth: false })
  }
  const data = response.status === 204 ? null : await response.json().catch(() => null)
  return options.withTotal ? { data, total: Number(response.headers.get('X-Total-Count')) } : data
}

// Downloads a file the API returns (e.g. the poster QR PNG) with the login token attached.
export async function download(path, filename) {
  const response = await send(path, {})
  if (!response.ok) await failure(response, {})
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
