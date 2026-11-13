<template>
    <!-- 重新寄送驗證信；同一信箱 60 秒內只能寄一次 (ER-US-A03) -->
    <div class="alert alert-info resend">
        <p>{{ prompt }}</p>
        <button class="btn btn-outline" type="button" :disabled="busy || waitSeconds > 0 || !email" @click="resend">
            {{ busy ? '寄送中…' : waitSeconds > 0 ? `請等待 ${waitSeconds} 秒` : '重新寄送驗證信' }}
        </button>
        <p v-if="message" :class="ok ? 'ok' : 'error'" role="status">{{ message }}</p>
    </div>
</template>

<script setup>
    import { onBeforeUnmount, ref } from 'vue'
    import { request } from '../api'

    const props = defineProps({
        email: { type: String, default: '' },
        prompt: { type: String, default: '尚未完成信箱驗證。沒收到信或連結已過期時，可以重新寄送。' },
    })
    const busy = ref(false)
    const message = ref('')
    const ok = ref(false)
    const waitSeconds = ref(0)
    let timer = null

    function countdown(seconds) {
        clearInterval(timer)
        waitSeconds.value = seconds
        timer = setInterval(() => {
            waitSeconds.value -= 1
            if (waitSeconds.value <= 0) clearInterval(timer)
        }, 1000)
    }

    async function resend() {
        busy.value = true
        message.value = ''
        try {
            await request('/auth/resend-verification', { method: 'POST', body: { email: props.email }, withAuth: false })
            ok.value = true
            message.value = '已重新寄送驗證信，舊的驗證連結將失效。請查看學校信箱。'
            countdown(60)
        } catch (e) {
            ok.value = false
            const seconds = e.detail && e.detail.retry_after_seconds
            message.value = seconds ? `寄送太頻繁，請於 ${seconds} 秒後再試。` : e.message
            if (seconds) countdown(seconds)
        } finally {
            busy.value = false
        }
    }

    onBeforeUnmount(() => clearInterval(timer))
</script>

<style scoped>
    .resend p {
        margin: 0 0 8px;
    }
    .resend .ok {
        color: var(--ok);
        margin: 8px 0 0;
    }
    .resend .error {
        color: var(--danger);
        margin: 8px 0 0;
    }
</style>
