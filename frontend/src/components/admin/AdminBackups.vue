<template>
    <!-- 最近 7 天的每日備份結果 (ER-US-J03) -->
    <section>
        <p v-if="loading" class="muted">載入中…</p>
        <p v-else-if="error" class="alert alert-error">{{ error }}</p>
        <template v-else>
            <p v-if="backups.length === 0" class="alert alert-info">最近 7 天沒有備份紀錄。請確認 worker 已啟動並設定 BACKUP_ENABLED=1。</p>
            <div v-else class="table-wrap">
                <table class="table">
                    <thead>
                        <tr><th>時間</th><th>結果</th><th>檔名</th><th>錯誤</th></tr>
                    </thead>
                    <tbody>
                        <tr v-for="backup in backups" :key="backup.id">
                            <td>{{ formatDateTime(backup.created_at) }}</td>
                            <td><span :class="['badge', (STATUS[backup.status] || STATUS.failed).tone]">{{ (STATUS[backup.status] || STATUS.failed).label }}</span></td>
                            <td>{{ backup.filename || '—' }}</td>
                            <td>{{ backup.error || '—' }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            <p class="muted small">還原只能由維運人員在伺服器上執行 (worker.py --restore)，步驟見 backend/docs/R2交接.md。</p>
        </template>
    </section>
</template>

<script setup>
    import { onMounted, ref } from 'vue'
    import { request } from '../../api'
    import { formatDateTime } from '../../format'

    const STATUS = {
        success: { label: '成功', tone: 'badge-ok' },
        running: { label: '進行中', tone: 'badge-info' },
        failed: { label: '失敗', tone: 'badge-danger' },
    }
    const backups = ref([])
    const loading = ref(true)
    const error = ref('')

    onMounted(async () => {
        try {
            backups.value = await request('/admin/backups')
        } catch (e) {
            error.value = e.message
        } finally {
            loading.value = false
        }
    })
</script>

<style scoped>
    .small {
        font-size: 0.88rem;
    }
</style>
