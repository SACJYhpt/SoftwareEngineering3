<template>
    <main class="page narrow">
        <form class="panel" novalidate @submit.prevent="onSubmit">
            <h1>建立活動</h1>
            <p class="muted">標示 <span class="required"></span> 的欄位為必填。時間皆為台灣時間。</p>

            <fieldset>
                <legend>基本資訊</legend>
                <div :class="['field', { invalid: errors.unit_id }]">
                    <label for="unit" class="required">主辦單位</label>
                    <select id="unit" v-model="form.unit_id" :disabled="managedUnits.length === 1">
                        <option disabled value="">請選擇</option>
                        <option v-for="unit in managedUnits" :key="unit.id" :value="unit.id">{{ unit.name }}</option>
                    </select>
                    <span v-if="errors.unit_id" class="error">{{ errors.unit_id }}</span>
                </div>
                <div :class="['field', { invalid: errors.name }]">
                    <label for="name" class="required">活動名稱</label>
                    <input id="name" v-model="form.name" maxlength="200" />
                    <span v-if="errors.name" class="error">{{ errors.name }}</span>
                </div>
                <div :class="['field', { invalid: errors.type }]">
                    <label for="type" class="required">活動類型</label>
                    <select id="type" v-model="form.type">
                        <option disabled value="">請選擇</option>
                        <option v-for="item in types" :key="item.id" :value="item.name">{{ item.name }}</option>
                    </select>
                    <span v-if="errors.type" class="error">{{ errors.type }}</span>
                </div>
                <div :class="['field', { invalid: errors.description }]">
                    <label for="description" class="required">活動描述</label>
                    <textarea id="description" v-model="form.description"></textarea>
                    <span v-if="errors.description" class="error">{{ errors.description }}</span>
                </div>
            </fieldset>

            <fieldset>
                <legend>時間與地點</legend>
                <div class="two-col">
                    <div :class="['field', { invalid: errors.start_time }]">
                        <label for="start" class="required">活動開始</label>
                        <input id="start" v-model="form.start_time" type="datetime-local" />
                        <span v-if="errors.start_time" class="error">{{ errors.start_time }}</span>
                    </div>
                    <div :class="['field', { invalid: errors.end_time }]">
                        <label for="end" class="required">活動結束</label>
                        <input id="end" v-model="form.end_time" type="datetime-local" />
                        <span v-if="errors.end_time" class="error">{{ errors.end_time }}</span>
                    </div>
                </div>
                <div :class="['field', { invalid: errors.location }]">
                    <label for="location" class="required">地點</label>
                    <input id="location" v-model="form.location" maxlength="255" />
                    <span v-if="errors.location" class="error">{{ errors.location }}</span>
                </div>
                <div class="two-col">
                    <div :class="['field', { invalid: errors.registration_start }]">
                        <label for="reg-start" class="required">報名開始</label>
                        <input id="reg-start" v-model="form.registration_start" type="datetime-local" />
                        <span v-if="errors.registration_start" class="error">{{ errors.registration_start }}</span>
                    </div>
                    <div :class="['field', { invalid: errors.registration_deadline }]">
                        <label for="reg-end" class="required">報名截止</label>
                        <input id="reg-end" v-model="form.registration_deadline" type="datetime-local" />
                        <span class="hint">截止時間當下起即不可報名，且不可晚於活動開始。</span>
                        <span v-if="errors.registration_deadline" class="error">{{ errors.registration_deadline }}</span>
                    </div>
                </div>
            </fieldset>

            <fieldset>
                <legend>報名規則與聯絡</legend>
                <div :class="['field', { invalid: errors.capacity }]">
                    <label for="capacity">名額上限</label>
                    <input id="capacity" v-model="form.capacity" type="number" min="1" step="1" inputmode="numeric" />
                    <span class="hint">留空表示不限名額。</span>
                    <span v-if="errors.capacity" class="error">{{ errors.capacity }}</span>
                </div>
                <div :class="['field', { invalid: errors.contact_information }]">
                    <label for="contact" class="required">聯絡方式</label>
                    <input id="contact" v-model="form.contact_information" maxlength="255" placeholder="例如：活動窗口 Email 或分機" />
                    <span v-if="errors.contact_information" class="error">{{ errors.contact_information }}</span>
                </div>
                <div class="field">
                    <label for="notes">注意事項</label>
                    <textarea id="notes" v-model="form.notes"></textarea>
                </div>
            </fieldset>

            <div v-if="formError" class="alert alert-error" role="alert">{{ formError }}</div>
            <button class="btn btn-large" type="submit" :disabled="submitting">{{ submitting ? '建立中…' : '建立並發布活動' }}</button>
        </form>
    </main>
</template>

<script setup>
    import { onMounted, reactive, ref } from 'vue'
    import { useRouter } from 'vue-router'
    import { request } from '../api'
    import { managedUnits } from '../auth'
    import { taipeiInputToDate, taipeiInputToIso } from '../format'

    const router = useRouter()
    const types = ref([])
    const submitting = ref(false)
    const formError = ref('')
    const FIELDS = ['unit_id', 'name', 'type', 'description', 'start_time', 'end_time', 'location',
                    'registration_start', 'registration_deadline', 'capacity', 'contact_information']
    const REQUIRED = FIELDS.filter((field) => field !== 'capacity')
    const form = reactive({
        unit_id: managedUnits.value.length === 1 ? managedUnits.value[0].id : '',
        name: '', type: '', description: '', start_time: '', end_time: '', location: '',
        registration_start: '', registration_deadline: '', capacity: '', contact_information: '', notes: '',
    })
    const errors = reactive(Object.fromEntries(FIELDS.map((field) => [field, ''])))

    // Same rules as the backend (ER-US-C03); the backend result is final.
    function validate() {
        for (const field of FIELDS) errors[field] = ''
        for (const field of REQUIRED) {
            if (String(form[field]).trim() === '') errors[field] = '此欄位為必填'
        }
        const start = taipeiInputToDate(form.start_time)
        const end = taipeiInputToDate(form.end_time)
        const regStart = taipeiInputToDate(form.registration_start)
        const regEnd = taipeiInputToDate(form.registration_deadline)
        if (start && start < new Date()) errors.start_time = '活動開始時間不可早於現在'
        if (start && end && end <= start) errors.end_time = '結束時間必須晚於開始時間'
        if (regStart && regEnd && regStart >= regEnd) errors.registration_start = '報名開始必須早於報名截止'
        if (regEnd && start && regEnd > start) errors.registration_deadline = '報名截止不可晚於活動開始'
        if (form.capacity !== '' && form.capacity !== null && !/^[1-9]\d*$/.test(String(form.capacity))) {
            errors.capacity = '名額須為正整數，或留空表示不限'
        }
        return FIELDS.every((field) => !errors[field])
    }

    const CODE_FIELDS = {
        EVENT_START_IN_PAST: 'start_time', UNIT_FORBIDDEN: 'unit_id', UNIT_NOT_FOUND: 'unit_id', EVENT_TYPE_INVALID: 'type',
    }

    async function onSubmit() {
        formError.value = ''
        if (!validate()) {
            formError.value = '請修正標示的欄位後再送出'
            return
        }
        submitting.value = true
        try {
            const payload = {
                unit_id: Number(form.unit_id),
                name: form.name, type: form.type, description: form.description,
                location: form.location, contact_information: form.contact_information,
                start_time: taipeiInputToIso(form.start_time), end_time: taipeiInputToIso(form.end_time),
                registration_start: taipeiInputToIso(form.registration_start),
                registration_deadline: taipeiInputToIso(form.registration_deadline),
                capacity: form.capacity === '' || form.capacity === null ? null : Number(form.capacity),
                notes: form.notes.trim() ? form.notes : null,
            }
            const event = await request('/events', { method: 'POST', body: payload })
            router.push(`/events/${event.id}`)
        } catch (e) {
            Object.assign(errors, e.fieldErrors || {})
            if (CODE_FIELDS[e.code]) errors[CODE_FIELDS[e.code]] = e.message
            formError.value = e.message
        } finally {
            submitting.value = false
        }
    }

    onMounted(async () => {
        try {
            types.value = await request('/event-types')
        } catch (e) {
            formError.value = '無法載入活動類型：' + e.message
        }
    })
</script>

<style scoped>
    .narrow {
        max-width: 760px;
    }
    h1 {
        margin-top: 0;
    }
    fieldset {
        border: none;
        border-top: 1px solid var(--border);
        margin: 20px 0 0;
        padding: 16px 0 0;
        min-width: 0;
    }
    legend {
        font-weight: 700;
        color: var(--brand);
        padding: 0 8px 0 0;
    }
    .two-col {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr));
        gap: 0 16px;
    }
</style>
