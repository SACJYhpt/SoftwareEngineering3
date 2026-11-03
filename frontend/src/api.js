// Thin wrapper around fetch for the FastAPI backend.
// Business errors arrive as {detail: {code, message}}; validation errors as {detail: [{loc, msg}]}.
import { auth, clearSession } from './auth'

const BASE = import.meta.env.VITE_API_BASE || '/api'

export class ApiError extends Error {
  constructor(status, code, message, fieldErrors = {}) {
    super(message)
    this.status = status
    this.code = code
    this.fieldErrors = fieldErrors
  }
}

// English validator messages from the backend, shown in Chinese.
const VALIDATION_MESSAGES = [
  ['end_time must be later than start_time', 'end_time', '結束時間必須晚於開始時間'],
  ['registration_start must be earlier than registration_deadline', 'registration_start', '報名開始必須早於報名截止'],
  ['registration_deadline must not be later than start_time', 'registration_deadline', '報名截止不可晚於活動開始'],
]

function toApiError(status, body) {
  const detail = body && body.detail
  if (detail && !Array.isArray(detail) && typeof detail === 'object') {
    return new ApiError(status, detail.code, detail.message || '發生錯誤')
  }
  if (Array.isArray(detail)) {
    const fieldErrors = {}
    for (const item of detail) {
      const known = VALIDATION_MESSAGES.find(([text]) => String(item.msg).includes(text))
      const field = known ? known[1] : item.loc && item.loc[1]
      fieldErrors[field || '_form'] = known ? known[2] : '此欄位格式不正確'
    }
    return new ApiError(status, 'VALIDATION_ERROR', '輸入資料有誤，請檢查標示的欄位', fieldErrors)
  }
  return new ApiError(status, 'HTTP_' + status, status >= 500 ? '伺服器發生錯誤，請稍後再試' : '發生錯誤')
}

export async function request(path, { method = 'GET', body, withAuth = true } = {}) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (withAuth && auth.token) headers.Authorization = 'Bearer ' + auth.token
  let response
  try {
    response = await fetch(BASE + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  } catch {
    throw new ApiError(0, 'NETWORK_ERROR', '無法連線到伺服器，請確認網路或後端是否啟動')
  }
  const data = response.status === 204 ? null : await response.json().catch(() => null)
  if (response.ok) return data
  const error = toApiError(response.status, data)
  if (error.code === 'INVALID_TOKEN') {
    clearSession()
    // Public pages stay readable after the session expires: retry once as a guest.
    if (method === 'GET' && withAuth) return request(path, { method, body, withAuth: false })
  }
  throw error
}
