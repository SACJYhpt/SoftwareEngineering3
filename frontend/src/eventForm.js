// Shared state and rules for the create (ER-US-C01) and edit (ER-US-F01) event forms.
import { isoToTaipeiInput, taipeiInputToDate, taipeiInputToIso } from './format'

export const EVENT_FIELDS = ['unit_id', 'name', 'type', 'description', 'start_time', 'end_time', 'location',
    'registration_start', 'registration_deadline', 'capacity', 'contact_information', 'notes']
const REQUIRED = EVENT_FIELDS.filter((field) => !['capacity', 'notes'].includes(field))
const TIME_FIELDS = ['start_time', 'end_time', 'registration_start', 'registration_deadline']

export function emptyEventForm(unitId = '') {
    return {
        unit_id: unitId, name: '', type: '', description: '', start_time: '', end_time: '', location: '',
        registration_start: '', registration_deadline: '', capacity: '', contact_information: '', notes: '',
    }
}

// Event from the API -> form values (times as Taiwan-time datetime-local strings).
export function eventToForm(event) {
    const form = emptyEventForm(event.unit_id)
    for (const field of EVENT_FIELDS) {
        if (field === 'unit_id') continue
        const value = event[field]
        form[field] = TIME_FIELDS.includes(field) ? isoToTaipeiInput(value) : value == null ? '' : String(value)
    }
    return form
}

// Same rules as the backend (ER-US-C02, C03): end after start, registration start before
// the deadline, deadline no later than the start. The backend result is final.
// checkPastStart: creating always checks it; editing only when the start time changed.
export function validateEventForm(form, errors, { checkPastStart = true } = {}) {
    for (const field of EVENT_FIELDS) errors[field] = ''
    for (const field of REQUIRED) {
        if (String(form[field]).trim() === '') errors[field] = '此欄位為必填'
    }
    const start = taipeiInputToDate(form.start_time)
    const end = taipeiInputToDate(form.end_time)
    const regStart = taipeiInputToDate(form.registration_start)
    const regEnd = taipeiInputToDate(form.registration_deadline)
    if (checkPastStart && start && start < new Date()) errors.start_time = '活動開始時間不可早於現在'
    if (start && end && end <= start) errors.end_time = '結束時間必須晚於開始時間'
    if (regStart && regEnd && regStart >= regEnd) errors.registration_start = '報名開始必須早於報名截止'
    if (regEnd && start && regEnd > start) errors.registration_deadline = '報名截止不可晚於活動開始'
    if (form.capacity !== '' && form.capacity !== null && !/^[1-9]\d*$/.test(String(form.capacity))) {
        errors.capacity = '名額須為正整數，或留空表示不限'
    }
    return EVENT_FIELDS.every((field) => !errors[field])
}

// Form values -> API body. With `original`, only changed fields are returned (PATCH).
export function eventFormToPayload(form, original = null) {
    const payload = {}
    for (const field of EVENT_FIELDS) {
        if (original && field === 'unit_id') continue
        if (original && String(form[field]).trim() === String(original[field]).trim()) continue
        const value = form[field]
        if (field === 'unit_id') payload[field] = Number(value)
        else if (TIME_FIELDS.includes(field)) payload[field] = taipeiInputToIso(value)
        else if (field === 'capacity') payload[field] = value === '' || value === null ? null : Number(value)
        else if (field === 'notes') payload[field] = String(value).trim() ? value : null
        else payload[field] = value
    }
    return payload
}

// Backend error codes that belong to one field.
export const EVENT_CODE_FIELDS = {
    EVENT_START_IN_PAST: 'start_time', UNIT_FORBIDDEN: 'unit_id', UNIT_NOT_FOUND: 'unit_id', UNIT_INACTIVE: 'unit_id',
    EVENT_TYPE_INVALID: 'type', CAPACITY_BELOW_REGISTRATIONS: 'capacity',
}
