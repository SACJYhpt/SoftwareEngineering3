<template>
    <!-- 寄信紀錄：自動重試 3 次仍失敗者可手動重寄 (ER-US-J02) -->
    <section>
        <div class="toolbar">
            <label>
                狀態
                <select v-model="status">
                    <option value="">全部</option>
                    <option v-for="(label, key) in STATUS_LABELS" :key="key" :value="key">{{ label }}</option>
                </select>
            </label>
            <button class="btn btn-outline btn-small" type="button" @click="load(1)">重新整理</button>
        </div>
        <p v-if="message" :class="['alert', message.ok ? 'alert-ok' : 'alert-error']" role="status">{{ message.text }}</p>
        <p v-if="loading" class="muted">載入中…</p>
        <p v-else-if="emails.length === 0" class="muted empty">沒有符合的寄信紀錄。</p>
        <div v-else class="table-wrap">
            <table class="table">
                <thead>
                    <tr><th>建立時間</th><th>收件者</th><th>主旨</th><th>狀態</th><th>嘗試次數</th><th>失敗紀錄</th><th></th></tr>
                </thead>
                <tbody>
                    <tr v-for="email in emails" :key="email.id">
                        <td>{{ formatDateTime(email.created_at) }}</td>
                        <td>{{ email.recipient }}</td>
                        <td>{{ email.subject }}</td>
                        <td><span :class="['badge', STATUS_TONES[email.status]]">{{ STATUS_LABELS[email.status] || email.status }}</span></td>
                        <td>{{ email.attempts }}</td>
                        <td>
                            <ul v-if="email.failures.length" class="failures">
                                <li v-for="(failure, index) in email.failures" :key="index">{{ formatDateTime(failure.at) }}：{{ failure.error }}</li>
                            </ul>
                            <span v-else class="muted">—</span>
                        </td>
                        <td>
                            <button v-if="email.status === 'failed'" class="btn btn-outline btn-small" type="button" :disabled="busy" @click="retry(email)">手動重寄</button>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
        <div class="pager">
            <button class="btn btn-outline btn-small" :disabled="page <= 1" @click="load(page - 1)">上一頁</button>
            <span>第 {{ page }} 頁</span>
            <button class="btn btn-outline btn-small" :disabled="emails.length < PAGE_SIZE" @click="load(page + 1)">下一頁</button>
        </div>
        <p class="muted small">信件由背景程式 (worker.py) 寄出；沒有啟動 worker 或沒有設定 SMTP 時，信件會停在「等待寄送」或「寄送失敗」。</p>
    </section>
</template>

<script setup>
    import { ref, watch } from 'vue'
    import { request } from '../../api'
    import { formatDateTime } from '../../format'

    const PAGE_SIZE = 20
    const STATUS_LABELS = { pending: '等待寄送', sending: '寄送中', sent: '已寄出', failed: '寄送失敗' }
    const STATUS_TONES = { pending: 'badge-info', sending: 'badge-info', sent: 'badge-ok', failed: 'badge-danger' }
    const status = ref('failed')
    const emails = ref([])
    const page = ref(1)
    const loading = ref(true)
    const busy = ref(false)
    const message = ref(null)

    async function load(target = page.value) {
        loading.value = true
        try {
            const params = new URLSearchParams({ page: target, page_size: PAGE_SIZE })
            if (status.value) params.set('status', status.value)
            emails.value = await request(`/admin/emails?${params}`)
            page.value = target
        } catch (e) {
            message.value = { ok: false, text: e.message }
        } finally {
            loading.value = false
        }
    }

    async function retry(email) {
        busy.value = true
        message.value = null
        try {
            await request(`/admin/emails/${email.id}/retry`, { method: 'POST' })
            message.value = { ok: true, text: `已將寄給 ${email.recipient} 的信重新排入寄送。` }
            await load()
        } catch (e) {
            message.value = { ok: false, text: e.message }
        } finally {
            busy.value = false
        }
    }

    watch(status, () => load(1), { immediate: true })
</script>

<style scoped>
    .toolbar {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 12px;
    }
    .toolbar label {
        display: flex;
        gap: 8px;
        align-items: center;
        font-weight: 600;
    }
    .toolbar select {
        padding: 6px 8px;
        border: 1px solid var(--border);
        border-radius: 6px;
    }
    .failures {
        margin: 0;
        padding-left: 18px;
        font-size: 0.88rem;
    }
    .pager {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 12px;
        margin-top: 12px;
    }
    .small {
        font-size: 0.88rem;
    }
    .empty {
        padding: 24px 0;
        text-align: center;
    }
</style>
