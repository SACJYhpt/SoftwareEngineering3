<template>
    <main class="page">
        <div class="page-head">
            <h1>活動管理</h1>
            <div class="head-actions">
                <router-link class="btn btn-outline" to="/organizer-terms">主辦規範</router-link>
                <router-link class="btn" to="/events/new">建立活動</router-link>
            </div>
        </div>
        <p class="muted">列出你所屬單位的所有活動，包含同單位其他管理者建立的活動 (單位：{{ managedUnits.map((u) => u.name).join('、') }})。</p>

        <div class="filters">
            <label>
                單位
                <select v-model="unitFilter">
                    <option value="">全部單位</option>
                    <option v-for="unit in managedUnits" :key="unit.id" :value="unit.id">{{ unit.name }}</option>
                </select>
            </label>
            <label class="check">
                <input v-model="showClosed" type="checkbox" />
                顯示已結束與已取消的活動
            </label>
        </div>

        <p v-if="message" :class="['alert', message.ok ? 'alert-ok' : 'alert-error']" role="status">{{ message.text }}</p>

        <!-- 取消活動：填寫原因並二次確認，通知所有報名者 (ER-US-F07) -->
        <form v-if="cancelling" class="panel cancel-panel" @submit.prevent="confirmCancel">
            <h2>取消活動：{{ cancelling.name }}</h2>
            <p class="muted">取消後停止所有報名，活動從首頁移除，並寄信通知所有已報名者。此操作無法復原。</p>
            <div :class="['field', { invalid: cancelError }]">
                <label for="reason" class="required">取消原因</label>
                <textarea id="reason" v-model="reason" maxlength="2000" placeholder="例如：颱風來襲，為安全起見取消活動"></textarea>
                <span v-if="cancelError" class="error">{{ cancelError }}</span>
            </div>
            <div class="row-actions">
                <button class="btn btn-danger" type="submit" :disabled="busy">{{ busy ? '取消中…' : '確認取消活動' }}</button>
                <button class="btn btn-outline" type="button" :disabled="busy" @click="cancelling = null">返回</button>
            </div>
        </form>

        <p v-if="loading" class="muted">載入中…</p>
        <p v-else-if="error" class="alert alert-error">{{ error }}</p>
        <p v-else-if="visible.length === 0" class="muted empty">沒有符合的活動。</p>
        <div v-else class="table-wrap">
            <table class="table">
                <thead>
                    <tr><th>活動</th><th>單位</th><th>活動時間</th><th>狀態</th><th>報名</th><th>操作</th></tr>
                </thead>
                <tbody>
                    <tr v-for="event in visible" :key="event.id">
                        <td><router-link :to="`/events/${event.id}`">{{ event.name }}</router-link></td>
                        <td>{{ event.unit.name }}</td>
                        <td>{{ formatDateTime(event.start_time) }}</td>
                        <td><span :class="['badge', 'badge-' + (STATUS_TONE[event.status] || 'muted')]">{{ event.status }}</span></td>
                        <td>{{ capacityText(event) }}</td>
                        <td class="ops">
                            <router-link class="btn btn-outline btn-small" :to="`/manage/events/${event.id}/registrations`">名單</router-link>
                            <template v-if="editable(event)">
                                <router-link class="btn btn-outline btn-small" :to="`/manage/events/${event.id}/edit`">修改</router-link>
                                <button class="btn btn-outline btn-small" type="button" @click="startCancel(event)">取消活動</button>
                            </template>
                            <button v-if="event.status !== '已取消'" class="btn btn-outline btn-small" type="button" @click="downloadQr(event)">QR Code</button>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
    </main>
</template>

<script setup>
    import { computed, onMounted, ref } from 'vue'
    import { download, request } from '../api'
    import { managedUnits } from '../auth'
    import { STATUS_TONE, capacityText, formatDateTime } from '../format'

    const events = ref([])
    const loading = ref(true)
    const error = ref('')
    const message = ref(null)
    const unitFilter = ref('')
    const showClosed = ref(false)
    const cancelling = ref(null)
    const reason = ref('')
    const cancelError = ref('')
    const busy = ref(false)

    // Upcoming first; the API lists newest first.
    const visible = computed(() => events.value
        .filter((event) => !unitFilter.value || event.unit_id === unitFilter.value)
        .filter((event) => showClosed.value || !['已結束', '已取消'].includes(event.status))
        .slice()
        .sort((a, b) => new Date(a.start_time) - new Date(b.start_time)))

    // Only events that are neither cancelled nor finished can be changed (ER-US-F01).
    function editable(event) {
        return !['已結束', '已取消'].includes(event.status)
    }

    async function load() {
        error.value = ''
        try {
            events.value = await request('/manage/events')
        } catch (e) {
            error.value = e.message
        } finally {
            loading.value = false
        }
    }

    function startCancel(event) {
        cancelling.value = event
        reason.value = ''
        cancelError.value = ''
        message.value = null
        window.scrollTo({ top: 0, behavior: 'smooth' })
    }

    async function confirmCancel() {
        cancelError.value = reason.value.trim() ? '' : '請填寫取消原因'
        if (cancelError.value) return
        if (!window.confirm(`確定要取消「${cancelling.value.name}」嗎？所有報名者都會收到取消通知。`)) return
        busy.value = true
        try {
            await request(`/events/${cancelling.value.id}/cancel`, { method: 'POST', body: { reason: reason.value.trim() } })
            message.value = { ok: true, text: `已取消「${cancelling.value.name}」，並排程通知所有報名者。` }
            cancelling.value = null
            await load()
        } catch (e) {
            cancelError.value = e.message
        } finally {
            busy.value = false
        }
    }

    async function downloadQr(event) {
        message.value = null
        try {
            await download(`/events/${event.id}/qr`, `event-${event.id}-qr.png`)
        } catch (e) {
            message.value = { ok: false, text: '無法下載 QR Code：' + e.message }
        }
    }

    onMounted(load)
</script>

<style scoped>
    .head-actions {
        display: flex;
        gap: 8px;
    }
    .filters {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 12px 24px;
        margin: 12px 0 16px;
    }
    .filters label {
        display: flex;
        align-items: center;
        gap: 8px;
        font-weight: 600;
    }
    .filters select {
        padding: 6px 8px;
        border: 1px solid var(--border);
        border-radius: 6px;
    }
    .ops {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
    }
    .cancel-panel {
        margin-bottom: 16px;
        border-color: var(--danger);
    }
    .cancel-panel h2 {
        margin-top: 0;
        font-size: 1.15rem;
    }
    .row-actions {
        display: flex;
        gap: 8px;
    }
    .empty {
        padding: 32px 0;
        text-align: center;
    }
</style>
