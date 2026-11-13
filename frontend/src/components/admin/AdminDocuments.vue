<template>
    <!-- 發布新版本：個資告知 (A02)、主辦規範 (I16)、常見問題 (B17)；舊版本保留 -->
    <section class="panel">
        <div class="kinds" role="radiogroup" aria-label="文件類型">
            <label v-for="(info, key) in KINDS" :key="key" :class="{ active: kind === key }">
                <input v-model="kind" type="radio" :value="key" /> {{ info.label }}
            </label>
        </div>
        <p class="muted">{{ KINDS[kind].hint }}</p>
        <p v-if="current" class="muted">目前為第 {{ current.version }} 版，發布於 {{ formatDateTime(current.published_at) }}。</p>
        <p v-else-if="!loading" class="alert alert-info">尚未發布。{{ KINDS[kind].missing }}</p>
        <div class="field">
            <label for="content" class="required">內容</label>
            <textarea id="content" v-model="content" rows="14"></textarea>
        </div>
        <p v-if="message" :class="['alert', message.ok ? 'alert-ok' : 'alert-error']" role="status">{{ message.text }}</p>
        <button class="btn" type="button" :disabled="busy || !content.trim() || unchanged" @click="publish">
            {{ busy ? '發布中…' : '發布為新版本' }}
        </button>
    </section>
</template>

<script setup>
    import { computed, ref, watch } from 'vue'
    import { request } from '../../api'
    import { formatDateTime } from '../../format'

    const KINDS = {
        privacy: { label: '個資告知', path: '/privacy-notice', hint: '註冊時顯示並要求同意。發布新版後，新註冊者須同意新版本。',
                   missing: '未發布前無法註冊。' },
        organizer: { label: '主辦規範', path: '/organizer-terms', hint: '活動管理者發布活動前須確認目前版本；發布新版後須重新確認，既有活動不受影響。',
                     missing: '未發布前無法建立活動。' },
        faq: { label: '常見問題', path: '/faq', hint: '內容須與目前已上線的規則一致（例如取消期限）。頁面會顯示最後更新時間。',
               missing: '' },
    }
    const kind = ref('privacy')
    const current = ref(null)
    const content = ref('')
    const loading = ref(true)
    const busy = ref(false)
    const message = ref(null)

    const unchanged = computed(() => current.value && current.value.content === content.value.trim())

    async function load() {
        loading.value = true
        message.value = null
        try {
            current.value = await request(KINDS[kind.value].path, { withAuth: false })
            content.value = current.value.content
        } catch (e) {
            current.value = null
            content.value = ''
            if (e.code !== 'DOCUMENT_NOT_PUBLISHED') message.value = { ok: false, text: e.message }
        } finally {
            loading.value = false
        }
    }

    async function publish() {
        if (!window.confirm(`確定要發布新版「${KINDS[kind.value].label}」嗎？`)) return
        busy.value = true
        try {
            const result = await request(`/admin/documents/${kind.value}`, { method: 'POST', body: { content: content.value } })
            await load() // clears the message, so set it afterwards
            message.value = { ok: true, text: `已發布第 ${result.version} 版。` }
        } catch (e) {
            message.value = { ok: false, text: e.message }
        } finally {
            busy.value = false
        }
    }

    watch(kind, load, { immediate: true })
</script>

<style scoped>
    .kinds {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 8px;
    }
    .kinds label {
        display: inline-flex;
        gap: 6px;
        align-items: center;
        padding: 6px 12px;
        border: 1px solid var(--border);
        border-radius: 999px;
        cursor: pointer;
        font-weight: 600;
    }
    .kinds label.active {
        border-color: var(--brand);
        color: var(--brand);
        background: var(--info-bg);
    }
</style>
