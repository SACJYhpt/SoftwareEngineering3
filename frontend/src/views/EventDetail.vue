<template>
    <main class="page">
        <router-link to="/" class="back-link">← 返回活動列表</router-link>

        <p v-if="loading" class="muted">載入中…</p>
        <div v-else-if="loadError" class="panel">
            <h1>{{ loadError.status === 404 ? '找不到這個活動' : '無法載入活動' }}</h1>
            <p class="muted">{{ loadError.status === 404 ? '活動可能不存在或尚未公開。' : loadError.message }}</p>
        </div>

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
                </dl>
                <section class="share-section">
                    <h2>分享活動</h2>
                    <p class="muted">此連結與海報 QR Code 僅導向活動詳情，不含登入憑證或個人資料；個人報到 QR Code 為另一種用途。</p>
                    <div class="share-link">
                        <input :value="shareUrl" readonly aria-label="活動詳情連結" />
                        <button class="btn btn-outline" type="button" @click="copyLink">複製連結</button>
                    </div>
                    <div class="qr-area">
                        <img :src="qrImageUrl" alt="活動詳情連結 QR Code" width="180" height="180" />
                        <span class="muted">海報 QR Code（活動詳情）</span>
                    </div>
                    <p v-if="shareMessage" class="muted" role="status">{{ shareMessage }}</p>
                </section>
                <h2>活動說明</h2>
                <p class="prose">{{ event.description }}</p>
                <template v-if="event.notes">
                    <h2>注意事項</h2>
                    <p class="prose">{{ event.notes }}</p>
                </template>
            </section>

            <aside class="panel action">
                <p v-if="event.my_registration_status" class="my-status">
                    我的報名狀態：<strong>{{ event.my_registration_status }}</strong>
                </p>
                <button class="btn btn-large" :disabled="!action.enabled || submitting" @click="onRegister">
                    {{ submitting ? '送出中…' : action.label }}
                </button>
                <p v-if="action.hint" class="muted hint">{{ action.hint }}</p>
                <div v-if="message" :class="['alert', message.ok ? 'alert-ok' : 'alert-error']" role="status">
                    {{ message.text }}
                </div>
            </aside>
        </div>
    </main>
</template>

<script setup>
    import { computed, ref, watch } from 'vue'
    import { useRoute, useRouter } from 'vue-router'
    import { request } from '../api'
    import { isLoggedIn } from '../auth'
    import { STATUS_TONE, capacityText, formatRange } from '../format'

    const route = useRoute()
    const router = useRouter()
    const event = ref(null)
    const loading = ref(true)
    const loadError = ref(null)
    const submitting = ref(false)
    const message = ref(null)
    const shareMessage = ref('')
    const shareUrl = computed(() => `${window.location.origin}/events/${route.params.id}`)
    const qrImageUrl = computed(() => `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(shareUrl.value)}`)

    async function copyLink() {
        try {
            await navigator.clipboard.writeText(shareUrl.value)
            shareMessage.value = '活動連結已複製'
        } catch {
            shareMessage.value = '無法自動複製，請手動複製上方連結'
        }
    }

    async function load() {
        loadError.value = null
        try {
            event.value = await request(`/events/${route.params.id}`)
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
        try {
            const result = await request(`/events/${route.params.id}/registrations`, { method: 'POST' })
            message.value = { ok: true, text: result.already_registered ? '你已經報名過這個活動。' : '報名成功！' }
        } catch (e) {
            if (e.code === 'AUTH_REQUIRED') {
                router.push({ path: '/login', query: { redirect: route.fullPath } })
                return
            }
            message.value = { ok: false, text: `報名失敗：${e.message}` }
        } finally {
            submitting.value = false
            await load()
        }
    }

    watch(() => route.params.id, () => {
        loading.value = true
        message.value = null
        load()
    }, { immediate: true })

    // Re-read personal status when the user logs in or out in another part of the page.
    watch(isLoggedIn, load)
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
        .share-link { flex-direction: column; }
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
    .share-section {
        margin-top: 24px;
        padding-top: 12px;
        border-top: 1px solid var(--border);
    }
    .share-link { display: flex; gap: 8px; }
    .share-link input { min-width: 0; flex: 1; padding: 8px; border: 1px solid var(--border); border-radius: 6px; }
    .qr-area { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; margin-top: 12px; }
    .qr-area img { border: 1px solid var(--border); padding: 6px; background: white; }
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
</style>
