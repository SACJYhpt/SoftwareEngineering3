<template>
    <main class="page narrow">
        <section class="panel">
            <h1>信箱驗證</h1>
            <p v-if="busy" class="muted">正在驗證…</p>
            <template v-else-if="ok">
                <p class="alert alert-ok">{{ message }}</p>
                <router-link class="btn btn-large" to="/login">前往登入</router-link>
            </template>
            <template v-else>
                <p class="alert alert-error">{{ message }}</p>
                <!-- 連結過期或已被新連結取代時，提供重新寄送 (ER-US-A03) -->
                <div class="field">
                    <label for="email">學校信箱</label>
                    <input id="email" v-model.trim="email" type="email" autocomplete="email" />
                </div>
                <ResendVerification :email="email" prompt="輸入註冊時的學校信箱，重新寄送驗證信。" />
                <router-link to="/login">返回登入</router-link>
            </template>
        </section>
    </main>
</template>

<script setup>
    import { onBeforeUnmount, onMounted, ref } from 'vue'
    import { request } from '../api'
    import { takeTokenFromHash } from '../format'
    import ResendVerification from '../components/ResendVerification.vue'

    const busy = ref(true)
    const ok = ref(false)
    const message = ref('')
    const email = ref('')

    async function verify() {
        const token = takeTokenFromHash()
        if (!token) {
            if (busy.value) {
                message.value = '連結不完整，請直接開啟驗證信中的連結。'
                busy.value = false
            }
            return
        }
        busy.value = true
        ok.value = false
        try {
            const result = await request('/auth/verify-email', { method: 'POST', body: { token }, withAuth: false })
            ok.value = true
            message.value = result.message + '，現在可以登入。'
        } catch (e) {
            message.value = e.code === 'LINK_INVALID' ? '連結已失效（已過期、已使用過，或已寄出較新的驗證信）。' : e.message
        } finally {
            busy.value = false
        }
    }

    // A second link opened in the same tab only changes the #hash, so the page is not reloaded.
    onMounted(() => {
        window.addEventListener('hashchange', verify)
        verify()
    })
    onBeforeUnmount(() => window.removeEventListener('hashchange', verify))
</script>

<style scoped>
    .narrow {
        max-width: 480px;
    }
    h1 {
        margin-top: 0;
    }
</style>
