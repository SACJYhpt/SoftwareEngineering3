// All times are shown and entered in Taiwan time (UTC+8), per the SRD common rules.
const formatter = new Intl.DateTimeFormat('zh-TW', {
  timeZone: 'Asia/Taipei',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  weekday: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

export function formatDateTime(iso) {
  return iso ? formatter.format(new Date(iso)) : ''
}

export function formatRange(startIso, endIso) {
  return `${formatDateTime(startIso)} – ${formatDateTime(endIso)}`
}

// <input type="datetime-local"> value ("2030-01-12T10:00") interpreted as Taiwan time.
export function taipeiInputToIso(value) {
  return value ? `${value}:00+08:00` : null
}

export function taipeiInputToDate(value) {
  return value ? new Date(taipeiInputToIso(value)) : null
}

export function capacityText(event) {
  return event.capacity == null ? `${event.registration_count} / 不限` : `${event.registration_count} / ${event.capacity}`
}

// Only allow redirects to paths inside this app (ER-US-D02): "/x" but not "//evil.com".
export function safeRedirect(value) {
  return typeof value === 'string' && value.startsWith('/') && !value.startsWith('//') && !value.startsWith('/\\')
    ? value
    : '/'
}

export const STATUS_TONE = {
  開放中: 'ok',
  報名未開始: 'info',
  已額滿: 'warn',
  已截止: 'muted',
  進行中: 'info',
  已結束: 'muted',
  已取消: 'danger',
}
