<template>
    <main class="page narrow">
        <router-link :to="`/events/${route.params.id}`" class="back-link">← 返回活動詳情</router-link>

        <p v-if="loading" class="muted">載入活動資料中…</p>
        <section v-else-if="loadError" class="panel">
            <h1>無法載入取消申請</h1>
            <p class="alert alert-error">{{ loadError }}</p>
        </section>

        <section v-else-if="event" class="panel">
            <h1>申請取消報名</h1>
            <h2 class="event-name">{{ event.name }}</h2>
            <p class="muted">活動時間：{{ formatRange(event.start_time, event.end_time) }}</p>

            <div v-if="pendingRequest" class="alert alert-info" role="status">
                這筆報名已有取消申請審核中，預計於 {{ formatDateTime(pendingRequest.auto_approve_at) }} 自動核准。
            </div>
            <div v-else-if="!event.can_request_cancellation" class="alert alert-info" role="status">
                目前不符合提出取消申請的條件。請回活動詳情確認最新報名狀態。
            </div>

            <form v-else novalidate @submit.prevent="submit">
                <p class="alert alert-info">
                    申請送出後，需等待管理者處理；等待核准期間其他活動可能額滿。若未在期限前處理，系統將於
                    送出後 72 小時或活動開始時間（兩者較早者）自動核准並取消這筆報名。
                </p>

                <div class="field" :class="{ invalid: reasonError }">
                    <label for="reason">取消原因<span class="required"></span></label>
                    <textarea id="reason" v-model="reason" rows="5" maxlength="2000" required
                        aria-describedby="reason-hint reason-error" placeholder="請簡要說明申請取消報名的原因"></textarea>
                    <span id="reason-hint" class="hint">最多 2000 字。{{ reason.length }}/2000</span>
                    <span v-if="reasonError" id="reason-error" class="error" role="alert">{{ reasonError }}</span>
                </div>

                <label class="confirm-row">
                    <input v-model="confirmed" type="checkbox" />
                    我了解申請可能需要等待處理，且未處理時會在上述時間自動核准。
                </label>

                <p v-if="submitError" class="alert alert-error" role="alert">{{ submitError }}</p>
                <button class="btn btn-large" type="submit" :disabled="submitting || !confirmed">
                    {{ submitting ? '送出中…' : '送出取消申請' }}
                </button>
            </form>
        </section>
    </main>
</template>

<script setup>
    import { computed, ref, watch } from 'vue'
    import { useRoute, useRouter } from 'vue-router'
    import { request } from '../api'
    import { formatDateTime, formatRange } from '../format'

    const route = useRoute()
    const router = useRouter()
    const event = ref(null)
    const loading = ref(true)
    const loadError = ref('')
    const reason = ref('')
    const attempted = ref(false)
    const confirmed = ref(false)
    const submitting = ref(false)
    const submitError = ref('')
    const reasonError = computed(() => attempted.value && !reason.value.trim() ? '請填寫取消原因。' : '')
    const pendingRequest = computed(() => event.value?.cancellation_request?.status === 'pending'
        ? event.value.cancellation_request : null)
    async function load() {
        loading.value = true
        loadError.value = ''
        try {
            event.value = await request(`/events/${route.params.id}`)
        } catch (error) {
            loadError.value = error.message
        } finally {
            loading.value = false
        }
    }

    async function submit() {
        attempted.value = true
        submitError.value = ''
        if (!reason.value.trim()) return
        if (!confirmed.value) {
            submitError.value = '請先確認你了解申請處理方式。'
            return
        }
        submitting.value = true
        try {
            await request(`/events/${route.params.id}/cancellation-requests`, {
                method: 'POST',
                body: { reason: reason.value.trim(), confirmed: true },
            })
            await router.replace(`/events/${route.params.id}`)
        } catch (error) {
            submitError.value = error.message
            if (error.code === 'CANCELLATION_REQUEST_PENDING') await load()
        } finally {
            submitting.value = false
        }
    }

    watch(() => route.params.id, load, { immediate: true })
</script>

<style scoped>
    .narrow {
        max-width: 760px;
    }
    .back-link {
        display: inline-block;
        margin-bottom: 16px;
        text-decoration: none;
        font-weight: 600;
    }
    h1 {
        margin: 0 0 12px;
    }
    .event-name {
        margin: 0;
        font-size: 1.15rem;
    }
    .confirm-row {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        margin: 20px 0;
    }
    .confirm-row input {
        margin-top: 6px;
        flex: 0 0 auto;
    }
</style>
