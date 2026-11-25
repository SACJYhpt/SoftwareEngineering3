<template>
    <main class="page">
        <router-link to="/manage" class="back-link">← 返回活動管理</router-link>

        <p v-if="loading" class="muted">載入中…</p>
        <section v-else-if="loadError" class="panel">
            <h1>無法載入取消申請</h1>
            <p class="alert alert-error">{{ loadError }}</p>
        </section>

        <template v-else>
            <div class="page-head">
                <div>
                    <h1>待處理取消申請</h1>
                    <p class="muted event-name">{{ event?.name }}</p>
                </div>
                <span class="badge badge-warn">{{ pending.length }} 件待處理</span>
            </div>

            <p v-if="feedback" :class="['alert', feedback.ok ? 'alert-ok' : 'alert-error']" role="status">
                {{ feedback.text }}
            </p>

            <p v-if="pending.length === 0" class="panel empty muted">目前沒有待處理的取消申請。</p>
            <ul v-else class="request-list">
                <li v-for="item in pending" :key="item.id" class="panel request-card">
                    <div class="request-head">
                        <div>
                            <span class="badge badge-warn">審核中</span>
                            <span class="request-id">申請 #{{ item.id }}</span>
                        </div>
                        <span class="muted small">報名紀錄 #{{ item.registration_id }}</span>
                    </div>
                    <dl class="facts">
                        <dt>申請人</dt>
                        <dd>{{ item.applicant_name || '姓名未提供' }}</dd>
                        <dt>申請原因</dt>
                        <dd class="reason">{{ item.reason }}</dd>
                        <dt>送出時間</dt>
                        <dd>{{ formatDateTime(item.submitted_at) }}</dd>
                        <dt>自動核准時間</dt>
                        <dd>{{ formatDateTime(item.auto_approve_at) }}</dd>
                    </dl>
                    <div class="actions">
                        <button class="btn" type="button" :disabled="busyId === item.id" @click="openReview(item, 'approve')">
                            核准
                        </button>
                        <button class="btn btn-outline reject" type="button" :disabled="busyId === item.id" @click="openReview(item, 'reject')">
                            拒絕
                        </button>
                    </div>
                </li>
            </ul>
        </template>

        <div v-if="reviewing" class="modal-backdrop" @click.self="closeReview">
            <section class="panel dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
                <h2 id="dialog-title">{{ reviewing.decision === 'approve' ? '核准取消申請？' : '拒絕取消申請？' }}</h2>
                <p class="muted">{{ reviewing.item.reason }}</p>
                <p v-if="reviewing.decision === 'approve'" class="alert alert-info">
                    核准後將取消該筆報名，並依系統規則處理名額與通知。
                </p>
                <form v-else novalidate @submit.prevent="submitReview">
                    <div class="field" :class="{ invalid: rejectAttempted && !rejectReason.trim() }">
                        <label for="reject-reason" class="required">拒絕原因</label>
                        <textarea id="reject-reason" v-model="rejectReason" rows="4" maxlength="2000" required
                            placeholder="請說明拒絕此申請的原因"></textarea>
                        <span v-if="rejectAttempted && !rejectReason.trim()" class="error" role="alert">請填寫拒絕原因。</span>
                    </div>
                </form>
                <p v-if="reviewError" class="alert alert-error" role="alert">{{ reviewError }}</p>
                <div class="dialog-actions">
                    <button v-if="reviewing.decision === 'approve'" class="btn" type="button" :disabled="busyId === reviewing.item.id" @click="submitReview">
                        {{ busyId === reviewing.item.id ? '處理中…' : '確認核准' }}
                    </button>
                    <button v-else class="btn reject" type="button" :disabled="busyId === reviewing.item.id" @click="submitReview">
                        {{ busyId === reviewing.item.id ? '處理中…' : '確認拒絕' }}
                    </button>
                    <button class="btn btn-outline" type="button" :disabled="busyId === reviewing.item.id" @click="closeReview">返回</button>
                </div>
            </section>
        </div>
    </main>
</template>

<script setup>
    import { computed, ref, watch } from 'vue'
    import { useRoute } from 'vue-router'
    import { request } from '../api'
    import { formatDateTime } from '../format'

    const route = useRoute()
    const event = ref(null)
    const requests = ref([])
    const loading = ref(true)
    const loadError = ref('')
    const feedback = ref(null)
    const reviewing = ref(null)
    const rejectReason = ref('')
    const rejectAttempted = ref(false)
    const reviewError = ref('')
    const busyId = ref(null)
    const pending = computed(() => requests.value.filter((item) => item.status === 'pending'))

    async function load() {
        loading.value = true
        loadError.value = ''
        try {
            const [eventData, requestData] = await Promise.all([
                request(`/events/${route.params.id}`),
                request(`/events/${route.params.id}/cancellation-requests`),
            ])
            event.value = eventData
            requests.value = requestData
        } catch (error) {
            loadError.value = error.message
        } finally {
            loading.value = false
        }
    }

    function openReview(item, decision) {
        reviewing.value = { item, decision }
        rejectReason.value = ''
        rejectAttempted.value = false
        reviewError.value = ''
    }

    function closeReview() {
        if (busyId.value !== null) return
        reviewing.value = null
    }

    async function submitReview() {
        if (!reviewing.value) return
        const { item, decision } = reviewing.value
        rejectAttempted.value = decision === 'reject'
        reviewError.value = ''
        if (decision === 'reject' && !rejectReason.value.trim()) return

        busyId.value = item.id
        try {
            const result = await request(`/cancellation-requests/${item.id}/review`, {
                method: 'POST',
                body: {
                    decision,
                    ...(decision === 'reject' ? { reason: rejectReason.value.trim() } : {}),
                },
            })
            const resultText = result.status === 'auto_approved'
                ? '申請已達自動核准時間，系統已自動核准。'
                : decision === 'approve' ? '已核准取消申請。' : '已拒絕取消申請。'
            reviewing.value = null
            feedback.value = { ok: true, text: resultText }
            await load()
        } catch (error) {
            reviewError.value = error.message
        } finally {
            busyId.value = null
        }
    }

    watch(() => route.params.id, load, { immediate: true })
</script>

<style scoped>
    .back-link {
        display: inline-block;
        margin-bottom: 16px;
        text-decoration: none;
        font-weight: 600;
    }
    .event-name {
        margin: 0;
    }
    .request-list {
        list-style: none;
        padding: 0;
        margin: 16px 0 0;
        display: grid;
        gap: 12px;
    }
    .request-card {
        padding: 20px;
    }
    .request-head,
    .request-head > div,
    .actions,
    .dialog-actions {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 8px;
    }
    .request-head {
        justify-content: space-between;
    }
    .request-id {
        margin-left: 8px;
        font-weight: 700;
    }
    .small {
        font-size: 0.88rem;
    }
    .facts {
        display: grid;
        grid-template-columns: max-content minmax(0, 1fr);
        gap: 6px 16px;
        margin: 18px 0;
    }
    .facts dt {
        color: var(--muted);
        font-weight: 600;
    }
    .facts dd {
        margin: 0;
        overflow-wrap: anywhere;
    }
    .reason {
        white-space: pre-line;
    }
    .actions {
        justify-content: flex-end;
    }
    .reject {
        border-color: var(--danger);
        color: var(--danger);
    }
    .reject:hover:not(:disabled) {
        background: var(--danger-bg);
    }
    .empty {
        text-align: center;
        padding: 32px;
    }
    .modal-backdrop {
        position: fixed;
        inset: 0;
        z-index: 20;
        display: grid;
        place-items: center;
        overflow-y: auto;
        padding: 20px;
        background: rgb(15 23 42 / 55%);
    }
    .dialog {
        width: min(100%, 560px);
        max-height: calc(100vh - 40px);
        overflow-y: auto;
    }
    .dialog h2 {
        margin-top: 0;
    }
    .dialog-actions {
        justify-content: flex-end;
        margin-top: 18px;
    }
</style>
