<template>
    <!-- 主辦規範：發布活動前須確認目前版本，與註冊時的個資告知分開 (ER-US-I16) -->
    <section class="terms panel">
        <h2>主辦規範<span v-if="terms">（第 {{ terms.version }} 版）</span></h2>
        <p v-if="error" class="alert alert-error">{{ error }}</p>
        <template v-else-if="terms">
            <p class="muted">發布：{{ formatDateTime(terms.published_at) }}</p>
            <div class="content">{{ terms.content }}</div>
            <label class="agree">
                <input v-model="agreed" type="checkbox" />
                我已閱讀並同意遵守上述主辦規範
            </label>
            <button class="btn" type="button" :disabled="!agreed || busy" @click="acknowledge">
                {{ busy ? '送出中…' : '確認主辦規範' }}
            </button>
            <p v-if="done" class="alert alert-ok">已確認第 {{ terms.version }} 版主辦規範。</p>
        </template>
        <p v-else class="muted">載入中…</p>
    </section>
</template>

<script setup>
    import { onMounted, ref } from 'vue'
    import { request } from '../api'
    import { formatDateTime } from '../format'

    const emit = defineEmits(['acknowledged'])
    const terms = ref(null)
    const agreed = ref(false)
    const busy = ref(false)
    const done = ref(false)
    const error = ref('')

    async function load() {
        try {
            terms.value = await request('/organizer-terms')
        } catch (e) {
            error.value = e.code === 'DOCUMENT_NOT_PUBLISHED' ? '主辦規範尚未發布，請聯絡系統管理員。' : e.message
        }
    }

    async function acknowledge() {
        busy.value = true
        error.value = ''
        try {
            await request('/organizer-terms/acknowledgements', { method: 'POST', body: { document_id: terms.value.id } })
            done.value = true
            emit('acknowledged')
        } catch (e) {
            if (e.code === 'DOCUMENT_OUTDATED') {
                // Updated while open: show the new version and ask again.
                agreed.value = false
                await load()
            }
            error.value = e.message
        } finally {
            busy.value = false
        }
    }

    onMounted(load)
</script>

<style scoped>
    .terms h2 {
        margin-top: 0;
        font-size: 1.15rem;
    }
    .content {
        max-height: 260px;
        overflow-y: auto;
        white-space: pre-line;
        padding: 12px;
        border: 1px solid var(--border);
        border-radius: 6px;
        background: var(--bg);
    }
    .agree {
        display: flex;
        gap: 8px;
        align-items: flex-start;
        margin: 12px 0;
        font-weight: 600;
    }
    .agree input {
        margin-top: 5px;
    }
</style>
