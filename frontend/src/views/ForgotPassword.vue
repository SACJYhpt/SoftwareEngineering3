<template>
    <main class="page narrow">
        <form class="panel" novalidate @submit.prevent="onSubmit">
            <h1>忘記密碼</h1>
            <p class="muted">輸入註冊時的學校信箱。若帳號存在，系統會寄出 1 小時內有效、只能使用一次的重設連結。</p>
            <div :class="['field', { invalid: error }]">
                <label for="email" class="required">學校信箱</label>
                <input id="email" v-model.trim="email" type="email" autocomplete="email" />
            </div>
            <p v-if="sent" class="alert alert-ok" role="status">若此信箱已註冊，重設連結已寄出，請查看學校信箱。</p>
            <p v-if="error" class="alert alert-error" role="alert">{{ error }}</p>
            <button class="btn btn-large" type="submit" :disabled="busy">{{ busy ? '送出中…' : '寄送重設連結' }}</button>
            <p class="note"><router-link to="/login">返回登入</router-link></p>
        </form>
    </main>
</template>

<script setup>
    import { ref } from 'vue'
    import { request } from '../api'

    const email = ref('')
    const busy = ref(false)
    const sent = ref(false)
    const error = ref('')

    async function onSubmit() {
        error.value = ''
        sent.value = false
        if (!email.value) {
            error.value = '請輸入學校信箱'
            return
        }
        busy.value = true
        try {
            // Same reply whether or not the account exists (ER-US-A08).
            await request('/auth/forgot-password', { method: 'POST', body: { email: email.value }, withAuth: false })
            sent.value = true
        } catch (e) {
            const seconds = e.detail && e.detail.retry_after_seconds
            error.value = seconds ? `寄送太頻繁，請於 ${seconds} 秒後再試。` : e.message
        } finally {
            busy.value = false
        }
    }
</script>

<style scoped>
    .narrow {
        max-width: 480px;
    }
    h1 {
        margin-top: 0;
    }
    .note {
        text-align: center;
        margin: 14px 0 0;
    }
</style>
