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

// API timestamp -> value for <input type="datetime-local"> in Taiwan time ("2030-01-12T10:00").
export function isoToTaipeiInput(iso) {
  if (!iso) return ''
  const shifted = new Date(new Date(iso).getTime() + 8 * 3600 * 1000)
  return shifted.toISOString().slice(0, 16)
}

export const IDENTITY_LABELS = { student: '學生', teacher: '教師', staff: '行政人員' }
export const ROLE_LABELS = { member: '一般使用者', manager: '活動管理者', admin: '系統管理員' }
export const UNIT_KIND_LABELS = { department: '系所', office: '行政單位', club: '社團' }
export const GRADES = [1, 2, 3, 4].map((n) => ({ value: n, label: `大學部 ${n} 年級` }))
  .concat([5, 6, 7].map((n) => ({ value: n, label: `研究所 ${n - 4} 年級` })))

const GRADE_LABEL_MAP = Object.fromEntries(GRADES.map((item) => [item.value, item.label]))

export function gradeLabel(grade) {
  const num = Number(grade)
  return GRADE_LABEL_MAP[num] || `${grade} 年級`
}

function resolveDepartmentNames(event, unitNameMap = null) {
  if (!Array.isArray(event?.eligibility_department_ids) || !event.eligibility_department_ids.length) return ''
  const mappedNames = unitNameMap
    ? event.eligibility_department_ids.map((id) => unitNameMap[id]).filter(Boolean)
    : []
  if (mappedNames.length === event.eligibility_department_ids.length) {
    return mappedNames.join('／')
  }
  const fromBackend = typeof event.eligibility_description === 'string'
    ? event.eligibility_description.split('；').find((seg) => seg.startsWith('系所／單位：'))
    : null
  if (fromBackend) return fromBackend.slice('系所／單位：'.length)
  return event.eligibility_department_ids.map((id) => `單位 #${id}`).join('／')
}

// Compose human-readable eligibility description using GRADES text labels (e.g. 5 -> 研究所 1 年級).
export function formatEligibilityDescription(event, unitNameMap = null) {
  if (!event) return '不限'
  const parts = []
  if (Array.isArray(event.eligibility_identities) && event.eligibility_identities.length) {
    parts.push('身分別：' + event.eligibility_identities.map((key) => IDENTITY_LABELS[key] || key).join('／'))
  }
  const deptText = resolveDepartmentNames(event, unitNameMap)
  if (deptText) {
    parts.push('系所／單位：' + deptText)
  }
  if (Array.isArray(event.eligibility_grades) && event.eligibility_grades.length) {
    parts.push('年級：' + event.eligibility_grades.map(gradeLabel).join('／'))
  }
  if (parts.length > 0) return parts.join('；')
  return event.eligibility_description || '不限'
}

// Concise headline for D03 eligibility mismatch notice, e.g. "本活動限 資訊工程學系 學生".
export function formatEligibilityHeadline(event, unitNameMap = null) {
  if (!event) return ''
  const deptText = resolveDepartmentNames(event, unitNameMap)
  const gradeText = Array.isArray(event.eligibility_grades) && event.eligibility_grades.length
    ? event.eligibility_grades.map(gradeLabel).join('／')
    : ''
  const identityText = Array.isArray(event.eligibility_identities) && event.eligibility_identities.length
    ? event.eligibility_identities.map((key) => IDENTITY_LABELS[key] || key).join('／')
    : ''
  const summary = [deptText, gradeText, identityText].filter(Boolean).join(' ')
  return summary ? `本活動限 ${summary}` : ''
}

// Token links arrive as /verify-email#token=...; read once, then drop it from the address bar.
export function takeTokenFromHash() {
  const token = new URLSearchParams(window.location.hash.slice(1)).get('token') || ''
  if (token) history.replaceState(history.state, '', window.location.pathname)
  return token
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
