<template>
    <main class="page narrow">
        <!-- 尚未確認目前版本的主辦規範時，先確認再建立 (ER-US-I16) -->
        <template v-if="needsTerms">
            <p class="alert alert-info">發布活動前，請先閱讀並確認目前版本的主辦規範。確認後會自動建立這個活動。</p>
            <OrganizerTermsPanel @acknowledged="onAcknowledged" />
        </template>

        <form v-show="!needsTerms" class="panel" novalidate @submit.prevent="onSubmit">
            <h1>建立活動</h1>
            <p class="muted">標示 <span class="required"></span> 的欄位為必填。時間皆為台灣時間。</p>
            <EventForm :form="form" :errors="errors" :units="managedUnits" :types="types" :unit-locked="managedUnits.length === 1" />
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
    import { EVENT_CODE_FIELDS, EVENT_FIELDS, emptyEventForm, eventFormToPayload, validateEventForm } from '../eventForm'
    import EventForm from '../components/EventForm.vue'
    import OrganizerTermsPanel from '../components/OrganizerTermsPanel.vue'

    const router = useRouter()
    const types = ref([])
    const submitting = ref(false)
    const formError = ref('')
    const needsTerms = ref(false)
    const form = reactive(emptyEventForm(managedUnits.value.length === 1 ? managedUnits.value[0].id : ''))
    const errors = reactive(Object.fromEntries(EVENT_FIELDS.map((field) => [field, ''])))

    async function onSubmit() {
        formError.value = ''
        if (!validateEventForm(form, errors)) {
            formError.value = '請修正標示的欄位後再送出'
            return
        }
        submitting.value = true
        try {
            const event = await request('/events', { method: 'POST', body: eventFormToPayload(form) })
            router.push(`/events/${event.id}`)
        } catch (e) {
            if (e.code === 'ORGANIZER_TERMS_REQUIRED') {
                needsTerms.value = true
                return
            }
            Object.assign(errors, e.fieldErrors || {})
            if (EVENT_CODE_FIELDS[e.code]) errors[EVENT_CODE_FIELDS[e.code]] = e.message
            formError.value = e.message
        } finally {
            submitting.value = false
        }
    }

    async function onAcknowledged() {
        needsTerms.value = false
        await onSubmit()
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
</style>
