<template>
    <main class="page">
        <h1>我的活動</h1>
        <div class="tabs" role="tablist">
            <button role="tab" :aria-selected="tab === 'upcoming'" :class="{ active: tab === 'upcoming' }" @click="tab = 'upcoming'">
                即將參加
            </button>
            <button role="tab" :aria-selected="tab === 'history'" :class="{ active: tab === 'history' }" @click="tab = 'history'">
                歷史紀錄
            </button>
        </div>

        <p v-if="loading" class="muted">載入中…</p>
        <p v-else-if="error" class="alert alert-error">{{ error }}</p>

        <!-- 已報名、尚未結束的活動，依開始時間排序 (ER-US-E01) -->
        <section v-else-if="tab === 'upcoming'">
            <p v-if="message" :class="['alert', message.ok ? 'alert-ok' : 'alert-error']" role="status">{{ message.text }}</p>
            <p v-if="upcoming.length === 0" class="muted empty">目前沒有即將參加的活動。<router-link to="/">去看看有哪些活動</router-link></p>
            <ul v-else class="list">
                <li v-for="event in upcoming" :key="event.id" class="panel row">
                    <div class="info">
                        <span :class="['badge', 'badge-' + (STATUS_TONE[event.status] || 'muted')]">{{ event.status }}</span>
                        <router-link :to="`/events/${event.id}`" class="name">{{ event.name }}</router-link>
                        <p class="muted">📅 {{ formatRange(event.start_time, event.end_time) }}</p>
                        <p class="muted">📍 {{ event.location }}　🏫 {{ event.unit.name }}</p>
                        <p class="muted">取消期限：{{ formatDateTime(event.registration_deadline) }} 前</p>
                    </div>
                    <div class="actions">
                        <span class="badge badge-ok">已報名</span>
                        <!-- 截止前可取消，需二次確認 (ER-US-E02) -->
                        <button v-if="event.can_cancel_registration" class="btn btn-outline" :disabled="busyId === event.id" @click="cancel(event)">
                            {{ busyId === event.id ? '取消中…' : '取消報名' }}
                        </button>
                        <span v-else class="muted small">已截止，無法取消</span>
                    </div>
                </li>
            </ul>
        </section>

        <!-- 已結束的活動與出席狀態 (ER-US-H03) -->
        <section v-else>
            <p v-if="history.length === 0" class="muted empty">還沒有參加過的活動。</p>
            <div v-else class="table-wrap">
                <table class="table">
                    <thead>
                        <tr><th>活動</th><th>日期</th><th>主辦單位</th><th>出席狀態</th></tr>
                    </thead>
                    <tbody>
                        <tr v-for="event in history" :key="event.id">
                            <td><router-link :to="`/events/${event.id}`">{{ event.name }}</router-link></td>
                            <td>{{ formatDateTime(event.start_time) }}</td>
                            <td>{{ event.unit.name }}</td>
                            <td>{{ event.attendance_status }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            <p class="muted small">報到功能上線前，出席狀態顯示「未記錄」。</p>
        </section>
    </main>
</template>

<script setup>
    import { onMounted, ref } from 'vue'
    import { request } from '../api'
    import { STATUS_TONE, formatDateTime, formatRange } from '../format'

    const tab = ref('upcoming')
    const upcoming = ref([])
    const history = ref([])
    const loading = ref(true)
    const error = ref('')
    const message = ref(null)
    const busyId = ref(null)

    async function load() {
        error.value = ''
        try {
            const [mine, past] = await Promise.all([request('/me/events'), request('/me/events/history')])
            upcoming.value = mine
            history.value = past
        } catch (e) {
            error.value = e.message
        } finally {
            loading.value = false
        }
    }

    async function cancel(event) {
        if (!window.confirm(`確定要取消報名「${event.name}」嗎？取消後名額會立即釋出。`)) return
        busyId.value = event.id
        message.value = null
        try {
            await request(`/events/${event.id}/registrations/me`, { method: 'DELETE' })
            message.value = { ok: true, text: `已取消「${event.name}」的報名。報名截止前仍可再次報名。` }
            await load()
        } catch (e) {
            message.value = { ok: false, text: `取消失敗：${e.message}` }
        } finally {
            busyId.value = null
        }
    }

    onMounted(load)
</script>

<style scoped>
    h1 {
        margin-top: 0;
    }
    .list {
        list-style: none;
        padding: 0;
        margin: 0;
        display: grid;
        gap: 12px;
    }
    .row {
        display: flex;
        flex-wrap: wrap;
        justify-content: space-between;
        gap: 12px;
        padding: 16px 20px;
    }
    .info {
        min-width: 0;
        flex: 1 1 280px;
    }
    .info p {
        margin: 2px 0;
        overflow-wrap: anywhere;
    }
    .name {
        display: block;
        font-size: 1.1rem;
        font-weight: 700;
        margin: 6px 0;
        overflow-wrap: anywhere;
    }
    .actions {
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        justify-content: center;
        gap: 8px;
    }
    .small {
        font-size: 0.88rem;
    }
    .empty {
        padding: 32px 0;
        text-align: center;
    }
</style>
