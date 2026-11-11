<template>
    <main class="page narrow">
        <router-link to="/manage" class="back-link">← 返回活動管理</router-link>
        <p v-if="loading" class="muted">載入中…</p>
        <div v-else-if="loadError" class="panel">
            <h1>無法修改這個活動</h1>
            <p class="muted">{{ loadError }}</p>
        </div>
        <!-- 修改活動；時間、地點或注意事項變更時，系統會通知已報名者 (ER-US-F01、F02) -->
        <form v-else class="panel" novalidate @submit.prevent="onSubmit">
            <h1>修改活動</h1>
            <p class="alert alert-info">修改活動時間、地點或注意事項後，系統會寄信通知所有已報名者，信中列出修改前後的內容。只修改其他欄位不會寄信。</p>
            <EventForm :form="form" :errors="errors" :units="units" :types="types" unit-locked editing />
            <div v-if="formError" class="alert alert-error" role="alert">{{ formError }}</div>
            <button class="btn btn-large" type="submit" :disabled="submitting">{{ submitting ? '儲存中…' : '儲存修改' }}</button>
        </form>
    </main>
</template>

<script setup>
    import { onMounted, reactive, ref } from 'vue'
    import { useRoute, useRouter } from 'vue-router'
    import { request } from '../api'
    import { EVENT_CODE_FIELDS, EVENT_FIELDS, emptyEventForm, eventFormToPayload, eventToForm, validateEventForm } from '../eventForm'
    import EventForm from '../components/EventForm.vue'

    const route = useRoute()
    const router = useRouter()
    const form = reactive(emptyEventForm())
    const errors = reactive(Object.fromEntries(EVENT_FIELDS.map((field) => [field, ''])))
    const units = ref([])
    const types = ref([])
    const loading = ref(true)
    const loadError = ref('')
    const formError = ref('')
    const submitting = ref(false)
    let original = null

    async function onSubmit() {
        formError.value = ''
        const startChanged = form.start_time !== original.start_time
        if (!validateEventForm(form, errors, { checkPastStart: startChanged })) {
            formError.value = '請修正標示的欄位後再送出'
            return
        }
        const changes = eventFormToPayload(form, original)
        if (Object.keys(changes).length === 0) {
            formError.value = '沒有任何變更'
            return
        }
        submitting.value = true
        try {
            await request(`/events/${route.params.id}`, { method: 'PATCH', body: changes })
            router.push(`/events/${route.params.id}`)
        } catch (e) {
            Object.assign(errors, e.fieldErrors || {})
            if (EVENT_CODE_FIELDS[e.code]) errors[EVENT_CODE_FIELDS[e.code]] = e.message
            formError.value = e.message
        } finally {
            submitting.value = false
        }
    }

    onMounted(async () => {
        try {
            const [event, typeList] = await Promise.all([request(`/events/${route.params.id}`), request('/event-types')])
            if (['已結束', '已取消'].includes(event.status)) {
                loadError.value = `活動${event.status}，不能再修改。`
                return
            }
            original = eventToForm(event)
            Object.assign(form, original)
            units.value = [event.unit]
            types.value = typeList
        } catch (e) {
            loadError.value = e.message
        } finally {
            loading.value = false
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
    .back-link {
        display: inline-block;
        margin-bottom: 16px;
        text-decoration: none;
        font-weight: 600;
    }
</style>
