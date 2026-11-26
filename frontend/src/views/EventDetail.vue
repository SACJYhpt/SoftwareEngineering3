<template>
    <main class="page">
        <router-link to="/" class="back-link">← 返回活動列表</router-link>

        <p v-if="loading" class="muted">載入中…</p>
        <div v-else-if="loadError" class="panel">
            <h1>{{ loadError.status === 404 ? '找不到這個活動' : '無法載入活動' }}</h1>
            <p class="muted">{{ loadError.status === 404 ? '活動可能不存在或尚未公開。' : loadError.message }}</p>
        </div>

        <section v-else-if="cancellationAction" class="panel cancel-landing">
            <h1>取消報名確認</h1>
            <h2 v-if="event" class="cancel-event-name">{{ event.name }}</h2>
            <p v-if="event" class="muted">活動時間：{{ formatRange(event.start_time, event.end_time) }}</p>
            <p>確認後會立即取消這筆報名。若你不想取消，請返回活動詳情即可。</p>
            <p v-if="cancellationAction.message" class="alert alert-info">{{ cancellationAction.message }}</p>
            <p v-if="cancellationActionError" class="alert alert-error" role="alert">{{ cancellationActionError }}</p>
            <div class="landing-actions">
                <button class="btn btn-danger" type="button" :disabled="actionSubmitting" @click="confirmLinkedCancellation">
                    {{ actionSubmitting ? '處理中…' : '確認取消報名' }}
                </button>
                <button class="btn btn-outline" type="button" :disabled="actionSubmitting" @click="dismissLinkedCancellation">
                    返回活動詳情
                </button>
            </div>
        </section>

        <div v-else-if="event" class="layout">
            <section class="panel info">
                <div class="badges">
                    <span :class="['badge', 'badge-' + (STATUS_TONE[event.status] || 'muted')]">{{ event.status }}</span>
                    <span class="badge badge-muted">{{ event.type }}</span>
                </div>
                <h1 class="title">{{ event.name }}</h1>
                <dl class="facts">
                    <dt>活動時間</dt>
                    <dd>{{ formatRange(event.start_time, event.end_time) }}</dd>
                    <dt>地點</dt>
                    <dd>{{ event.location }}</dd>
                    <dt>主辦單位</dt>
                    <dd>{{ event.unit.name }}</dd>
                    <dt>聯絡方式</dt>
                    <dd>{{ event.contact_information }}</dd>
                    <dt>報名期間</dt>
                    <dd>{{ formatRange(event.registration_start, event.registration_deadline) }}</dd>
                    <dt>名額</dt>
                    <dd>{{ capacityText(event) }}</dd>
                    <dt>報名資格</dt>
                    <dd>{{ event.eligibility_description || '不限' }}</dd>
                </dl>
                <div v-if="event.status === '已取消' && event.cancellation_reason" class="alert alert-error">
                    活動已取消。取消原因：{{ event.cancellation_reason }}
                </div>
                <h2>活動說明</h2>
                <p class="prose">{{ event.description }}</p>
                <template v-if="event.notes">
                    <h2>注意事項</h2>
                    <p class="prose">{{ event.notes }}</p>
                </template>

                <!-- 固定連結給所有人；海報 QR Code 只給該單位的活動管理者 (ER-US-B11) -->
                <section class="share">
                    <h2>分享活動</h2>
                    <div class="share-link">
                        <input :value="shareUrl" readonly aria-label="活動連結" @focus="$event.target.select()" />
                        <button class="btn btn-outline" type="button" @click="copyLink">複製連結</button>
                    </div>
                    <button v-if="canManage && event.status !== '已取消'" class="btn btn-outline qr" type="button" @click="downloadQr">下載海報 QR Code</button>
                    <p v-if="shareMessage" class="muted" role="status">{{ shareMessage }}</p>
                </section>
            </section>

            <aside class="panel action">
                <p v-if="event.my_registration_status" class="my-status">
                    我的報名狀態：<strong>{{ event.my_registration_status }}</strong>
                </p>
                <div v-if="cancellationActionError" class="alert alert-error" role="alert">
                    {{ cancellationActionError }}
                    <button v-if="actionRetryable" class="btn btn-outline btn-small retry-action" type="button" @click="resolveCancellationLink">重試</button>
                </div>
                <div v-if="hasPendingCancellation" class="alert alert-info" role="status">
                    取消申請審核中。若管理者尚未處理，系統將於 {{ formatDateTime(event.cancellation_request.auto_approve_at) }} 自動核准。
                </div>
                <button class="btn btn-large" :disabled="!action.enabled || submitting" @click="onRegister">
                    {{ submitting ? '送出中…' : action.label }}
                </button>
                <p v-if="action.hint" class="muted hint">{{ action.hint }}</p>
                <!-- 截止前取消報名，需二次確認 (ER-US-E02) -->
                <template v-if="event.my_registration_status === '已報名'">
                    <p v-if="event.can_cancel_registration && event.direct_cancel_deadline" class="muted hint cancel-deadline">
                        可直接取消至 {{ formatDateTime(event.direct_cancel_deadline) }} 前。
                    </p>
                    <button v-if="event.can_cancel_registration" class="btn btn-outline btn-large cancel" :disabled="submitting" @click="onCancel">
                        取消報名
                    </button>
                    <router-link v-else-if="event.can_request_cancellation" class="btn btn-outline btn-large cancel" :to="cancellationRequestPath">
                        申請取消
                    </router-link>
                    <p v-else-if="!hasPendingCancellation" class="muted hint">目前無法取消報名或提出取消申請。</p>
                </template>
                <div v-if="message" :class="['alert', message.ok ? 'alert-ok' : 'alert-error']" role="status">
                    {{ message.text }}
                </div>
                <!-- 報名資格不符提示 (ER-US-D03) -->
                <div v-if="eligibilityError" class="alert alert-error eligibility-error" role="alert">
                    <strong>不符合報名資格</strong>
                    <ul v-if="eligibilityError.conditions.length" class="eligibility-conditions">
                        <li v-for="condition in eligibilityError.conditions" :key="condition">{{ condition }}</li>
                    </ul>
                    <p class="eligibility-summary">{{ eligibilityError.message }}</p>
                    <p v-if="event.eligibility_description && event.eligibility_description !== '不限'" class="eligibility-requirement">
                        本活動資格限制：{{ event.eligibility_description }}
                    </p>
                    <p class="eligibility-profile-link">
                        <router-link to="/me/profile">前往更新個人資料</router-link>
                    </p>
                </div>
            </aside>
        </div>
    </main>
</template>

<script setup>
    import { computed, ref, watch } from 'vue'
    import { useRoute, useRouter } from 'vue-router'
    import { download, request } from '../api'
    import { isLoggedIn, managedUnits } from '../auth'
    import { STATUS_TONE, capacityText, formatDateTime, formatRange } from '../format'

    const route = useRoute()
    const router = useRouter()
    const event = ref(null)
    const loading = ref(true)
    const loadError = ref(null)
    const submitting = ref(false)
    const actionSubmitting = ref(false)
    const cancellationAction = ref(null)
    const cancellationActionError = ref('')
    const actionRetryable = ref(false)
    const message = ref(null)
    const eligibilityError = ref(null)
    const shareMessage = ref('')
    const CANCEL_ACTION_TOKEN_KEY = 'ntou-cancellation-action-token'
    let resolvingCancellationLink = false

    const shareUrl = computed(() => `${window.location.origin}/events/${route.params.id}`)
    const cancellationRequestPath = computed(() => `/events/${route.params.id}/cancellation-request`)
    const hasPendingCancellation = computed(() => event.value?.cancellation_request?.status === 'pending')
    const canManage = computed(() => event.value && managedUnits.value.some((unit) => unit.id === event.value.unit_id))

    function captureCancellationToken() {
        if (!window.location.hash) return
        const token = new URLSearchParams(window.location.hash.slice(1)).get('cancel_token')
        if (!token) return
        try {
            sessionStorage.setItem(CANCEL_ACTION_TOKEN_KEY, token)
        } catch {
            cancellationActionError.value = '瀏覽器無法暫存通知連結，請重新開啟信件中的連結。'
        }
        // Keep the action token out of the visible URL and browser history immediately.
        window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}`)
    }

    function savedCancellationToken() {
        try {
            return sessionStorage.getItem(CANCEL_ACTION_TOKEN_KEY)
        } catch {
            return null
        }
    }

    function clearCancellationToken() {
        try {
            sessionStorage.removeItem(CANCEL_ACTION_TOKEN_KEY)
        } catch {
            // The token is also removed from the URL; storage may be unavailable in private mode.
        }
    }

    async function resolveCancellationLink() {
        if (resolvingCancellationLink) return
        const token = savedCancellationToken()
        if (!token) return
        if (!isLoggedIn.value) {
            await router.replace({ path: '/login', query: { redirect: `/events/${route.params.id}` } })
            return
        }

        resolvingCancellationLink = true
        cancellationActionError.value = ''
        actionRetryable.value = false
        try {
            const result = await request('/me/cancellation-action', { method: 'POST', body: { token } })
            if (Number(result.event_id) !== Number(route.params.id) || result.confirmation_required !== true) {
                clearCancellationToken()
                cancellationActionError.value = '取消連結資料不完整或與目前活動不符。'
                return
            }
            if (result.action === 'cancel' && result.method === 'DELETE'
                && result.path === `/events/${route.params.id}/registrations/me`) {
                cancellationAction.value = result
                return
            }
            if (result.action === 'request_cancellation' && result.method === 'POST'
                && result.path === `/events/${route.params.id}/cancellation-requests`) {
                clearCancellationToken()
                await router.replace(`/events/${route.params.id}/cancellation-request?fromNotification=1`)
                return
            }
            clearCancellationToken()
            cancellationActionError.value = '取消連結提供了無法辨識的操作。'
        } catch (error) {
            if (error.code === 'AUTH_REQUIRED' || error.code === 'INVALID_TOKEN') {
                await router.replace({ path: '/login', query: { redirect: `/events/${route.params.id}` } })
            } else if (error.code === 'CANCELLATION_LINK_INVALID') {
                clearCancellationToken()
                cancellationActionError.value = '這個取消連結已失效、已處理，或不屬於目前登入的帳號。'
            } else {
                cancellationActionError.value = error.message
                actionRetryable.value = true
            }
        } finally {
            resolvingCancellationLink = false
        }
    }

    async function confirmLinkedCancellation() {
        if (!cancellationAction.value || actionSubmitting.value) return
        actionSubmitting.value = true
        cancellationActionError.value = ''
        try {
            await request(cancellationAction.value.path, { method: cancellationAction.value.method })
            clearCancellationToken()
            cancellationAction.value = null
            message.value = { ok: true, text: '已依通知連結取消報名。' }
            await load()
        } catch (error) {
            if (error.code === 'INVALID_TOKEN' || error.code === 'AUTH_REQUIRED') {
                await router.replace({ path: '/login', query: { redirect: `/events/${route.params.id}` } })
            } else {
                // Rechecking the token will switch to the application flow if the cutoff passed.
                cancellationAction.value = null
                cancellationActionError.value = error.message
                await resolveCancellationLink()
            }
        } finally {
            actionSubmitting.value = false
        }
    }

    async function dismissLinkedCancellation() {
        clearCancellationToken()
        cancellationAction.value = null
        await router.replace(`/events/${route.params.id}`)
    }

    async function copyLink() {
        try {
            await navigator.clipboard.writeText(shareUrl.value)
            shareMessage.value = '已複製活動連結'
        } catch {
            shareMessage.value = '無法自動複製，請手動選取上方連結'
        }
    }

    async function downloadQr() {
        shareMessage.value = ''
        try {
            await download(`/events/${route.params.id}/qr`, `event-${route.params.id}-qr.png`)
        } catch (e) {
            shareMessage.value = '無法下載 QR Code：' + e.message
        }
    }

    async function onCancel() {
        if (!window.confirm('確定要取消報名嗎？取消後名額會立即釋出。')) return
        submitting.value = true
        message.value = null
        eligibilityError.value = null
        try {
            await request(`/events/${route.params.id}/registrations/me`, { method: 'DELETE' })
            message.value = { ok: true, text: '已取消報名。報名截止前仍可再次報名。' }
        } catch (e) {
            message.value = { ok: false, text: `取消失敗：${e.message}` }
        } finally {
            submitting.value = false
            await load()
        }
    }

    async function load() {
        loading.value = true
        loadError.value = null
        try {
            event.value = await request(`/events/${route.params.id}`, { guestRetry: true })
        } catch (e) {
            loadError.value = e
        } finally {
            loading.value = false
        }
    }

    // The button only reflects the server's view; the registration API re-checks everything.
    const action = computed(() => {
        const e = event.value
        if (e.my_registration_status === '已報名') return { enabled: false, label: '已報名' }
        if (e.status === '開放中') {
            return isLoggedIn.value
                ? { enabled: e.can_register, label: '立即報名' }
                : { enabled: true, label: '登入後報名', hint: '報名前需要先登入，登入後會回到這個頁面。' }
        }
        const period = `報名期間：${formatRange(e.registration_start, e.registration_deadline)}`
        const reasons = {
            報名未開始: { label: '報名尚未開始', hint: period },
            已截止: { label: '報名已截止', hint: period },
            已額滿: { label: '名額已滿' },
            進行中: { label: '活動進行中' },
            已結束: { label: '活動已結束' },
            已取消: { label: '活動已取消' },
        }
        return { enabled: false, ...(reasons[e.status] || { label: '無法報名' }) }
    })

    async function onRegister() {
        if (!isLoggedIn.value) {
            router.push({ path: '/login', query: { redirect: route.fullPath } })
            return
        }
        submitting.value = true
        message.value = null
        eligibilityError.value = null
        try {
            const result = await request(`/events/${route.params.id}/registrations`, { method: 'POST' })
            message.value = { ok: true, text: result.already_registered ? '你已經報名過這個活動。' : '報名成功！' }
        } catch (e) {
            if (e.code === 'AUTH_REQUIRED') {
                router.push({ path: '/login', query: { redirect: route.fullPath } })
                return
            }
            if (e.code === 'ELIGIBILITY_MISMATCH') {
                eligibilityError.value = {
                    message: e.message,
                    conditions: Array.isArray(e.detail?.conditions) ? e.detail.conditions : [],
                }
                return
            }
            message.value = { ok: false, text: `報名失敗：${e.message}` }
        } finally {
            submitting.value = false
            await load()
        }
    }

    async function initialize() {
        captureCancellationToken()
        loading.value = true
        message.value = null
        eligibilityError.value = null
        await load()
        await resolveCancellationLink()
    }

    watch(() => route.params.id, initialize, { immediate: true })

    // Re-read personal status when the user logs in or out in another part of the page.
    watch(isLoggedIn, async (loggedIn) => {
        await load()
        if (loggedIn) await resolveCancellationLink()
    })
</script>

<style scoped>
    .back-link {
        display: inline-block;
        margin-bottom: 16px;
        text-decoration: none;
        font-weight: 600;
    }
    .layout {
        display: grid;
        grid-template-columns: minmax(0, 1fr) 300px;
        gap: 20px;
        align-items: start;
    }
    @media (max-width: 800px) {
        .layout {
            grid-template-columns: minmax(0, 1fr);
        }
        .action {
            order: -1;
        }
    }
    .badges {
        display: flex;
        gap: 6px;
        flex-wrap: wrap;
    }
    .title {
        margin: 10px 0 16px;
        overflow-wrap: anywhere;
    }
    .facts {
        display: grid;
        grid-template-columns: max-content minmax(0, 1fr);
        gap: 6px 16px;
        margin: 0 0 20px;
    }
    .facts dt {
        color: var(--muted);
        font-weight: 600;
    }
    .facts dd {
        margin: 0;
        overflow-wrap: anywhere;
    }
    h2 {
        font-size: 1.1rem;
        margin: 20px 0 6px;
    }
    .prose {
        white-space: pre-line;
        margin: 0;
        overflow-wrap: anywhere;
    }
    .action {
        position: sticky;
        top: 76px;
    }
    .my-status {
        margin: 0 0 12px;
    }
    .hint {
        margin: 10px 0 0;
        font-size: 0.9rem;
    }
    .cancel {
        margin-top: 12px;
    }
    .cancel-landing {
        max-width: 700px;
        margin: 24px auto;
    }
    .cancel-landing h1 {
        margin-top: 0;
    }
    .cancel-event-name {
        margin: 0;
    }
    .landing-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 20px;
    }
    .retry-action {
        margin-left: 8px;
    }
    .share {
        margin-top: 24px;
        padding-top: 8px;
        border-top: 1px solid var(--border);
    }
    .share-link {
        display: flex;
        gap: 8px;
    }
    .share-link input {
        flex: 1;
        min-width: 0;
        padding: 8px 10px;
        border: 1px solid var(--border);
        border-radius: 6px;
        background: var(--bg);
    }
    .qr {
        margin-top: 10px;
    }
    .eligibility-error {
        margin-top: 12px;
    }
    .eligibility-conditions {
        margin: 6px 0;
        padding-left: 20px;
    }
    .eligibility-summary,
    .eligibility-requirement,
    .eligibility-profile-link {
        margin: 6px 0 0;
        font-size: 0.92rem;
    }
</style>
