<template>
    <!-- 常見問題，不需登入；內容由系統管理員發布 (ER-US-B17) -->
    <main class="page narrow">
        <section class="panel">
            <h1>常見問題</h1>
            <p v-if="loading" class="muted">載入中…</p>
            <p v-else-if="error" class="alert alert-error">{{ error }}</p>
            <template v-else>
                <p class="muted">最後更新：{{ formatDateTime(faq.published_at) }}（第 {{ faq.version }} 版）</p>
                <div class="content">{{ faq.content }}</div>
            </template>
        </section>
    </main>
</template>

<script setup>
    import { onMounted, ref } from 'vue'
    import { request } from '../api'
    import { formatDateTime } from '../format'

    const faq = ref(null)
    const loading = ref(true)
    const error = ref('')

    onMounted(async () => {
        try {
            faq.value = await request('/faq', { withAuth: false })
        } catch (e) {
            error.value = e.code === 'DOCUMENT_NOT_PUBLISHED' ? '常見問題尚未發布。' : e.message
        } finally {
            loading.value = false
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
    .content {
        white-space: pre-line;
        line-height: 1.8;
    }
</style>
