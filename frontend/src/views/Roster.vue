<template>
    <main class="page">
        <router-link to="/manage" class="back-link">← 返回活動管理</router-link>
        <p v-if="loading" class="muted">載入中…</p>
        <p v-else-if="error" class="alert alert-error">{{ error }}</p>
        <!-- 正式報名名單，依報名時間排序；只有活動所屬單位的管理者能查看 (ER-US-G01) -->
        <template v-else>
            <div class="page-head">
                <h1>報名名單：{{ event.name }}</h1>
                <span class="badge badge-info">正式報名 {{ capacityText(event) }}</span>
            </div>
            <p class="muted">名單含個人資料，僅供辦理本活動使用。</p>
            <p v-if="roster.registrations.length === 0" class="muted empty">目前還沒有人報名。</p>
            <div v-else class="table-wrap">
                <table class="table">
                    <thead>
                        <tr><th>#</th><th>姓名</th><th>Email</th><th>身分別</th><th>系所／單位</th><th>年級</th><th>報名時間</th></tr>
                    </thead>
                    <tbody>
                        <tr v-for="(person, index) in roster.registrations" :key="person.registration_id">
                            <td>{{ index + 1 }}</td>
                            <td>{{ person.name }}</td>
                            <td>{{ person.email }}</td>
                            <td>{{ IDENTITY_LABELS[person.identity] || '—' }}</td>
                            <td>{{ person.department ? person.department.name : '—' }}</td>
                            <td>{{ person.grade || '—' }}</td>
                            <td>{{ formatDateTime(person.registered_at) }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </template>
    </main>
</template>

<script setup>
    import { onMounted, ref } from 'vue'
    import { useRoute } from 'vue-router'
    import { request } from '../api'
    import { IDENTITY_LABELS, capacityText, formatDateTime } from '../format'

    const route = useRoute()
    const event = ref(null)
    const roster = ref(null)
    const loading = ref(true)
    const error = ref('')

    onMounted(async () => {
        try {
            const [detail, list] = await Promise.all([
                request(`/events/${route.params.id}`),
                request(`/events/${route.params.id}/registrations`),
            ])
            event.value = detail
            roster.value = list
        } catch (e) {
            error.value = e.status === 403 ? '你不是這個活動所屬單位的管理者，無法查看名單。' : e.message
        } finally {
            loading.value = false
        }
    })
</script>

<style scoped>
    .back-link {
        display: inline-block;
        margin-bottom: 16px;
        text-decoration: none;
        font-weight: 600;
    }
    .empty {
        padding: 32px 0;
        text-align: center;
    }
</style>
