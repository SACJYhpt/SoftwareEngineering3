<template>
    <main class="page narrow">
        <form class="panel" novalidate @submit.prevent="onSubmit">
            <h1>登入</h1>
            <p v-if="route.query.redirect && route.query.redirect !== '/'" class="alert alert-info">請先登入，登入後會回到原本的頁面。</p>
            <div :class="['field', { invalid: errors.email }]">
                <label for="email" class="required">學校信箱</label>
                <input id="email" v-model="email" type="email" autocomplete="username" />
                <span v-if="errors.email" class="error">{{ errors.email }}</span>
            </div>
            <div :class="['field', { invalid: errors.password }]">
                <label for="password" class="required">密碼</label>
                <input id="password" v-model="password" type="password" autocomplete="current-password" />
                <span v-if="errors.password" class="error">{{ errors.password }}</span>
            </div>
            <div v-if="formError" class="alert alert-error" role="alert">{{ formError }}</div>
            <button class="btn btn-large" type="submit" :disabled="submitting">{{ submitting ? '登入中…' : '登入' }}</button>
            <div class="login-links"><router-link to="/forgot-password">忘記密碼？</router-link></div>
            <div v-if="verificationNeeded" class="alert alert-info">
                尚未完成信箱驗證。<button class="text-button" type="button" :disabled="resending" @click="resend">{{ resending ? '寄送中…' : '重新寄送驗證信' }}</button>
            </div>
            <p class="muted note">還沒有帳號？<router-link to="/register">立即註冊</router-link></p>
        </form>
    </main>
</template>

<script setup>
    import { reactive, ref } from 'vue'
    import { useRoute, useRouter } from 'vue-router'
    import { login } from '../auth'
    import { request } from '../api'
    import { safeRedirect } from '../format'

    const route = useRoute()
    const router = useRouter()
    const email = ref('')
    const password = ref('')
    const errors = reactive({ email: '', password: '' })
    const formError = ref('')
    const submitting = ref(false)
    const verificationNeeded = ref(false)
    const resending = ref(false)

    async function resend() {
        resending.value = true
        try {
            const result = await request('/auth/resend-verification', {
                method: 'POST', body: { email: email.value.trim() }, withAuth: false,
            })
            formError.value = result.message
            verificationNeeded.value = false
        } catch (e) { formError.value = e.message }
        finally { resending.value = false }
    }

    async function onSubmit() {
        errors.email = email.value.trim() ? '' : '請輸入信箱'
        errors.password = password.value ? '' : '請輸入密碼'
        formError.value = ''
        verificationNeeded.value = false
        if (errors.email || errors.password) return
        submitting.value = true
        try {
            await login(email.value.trim(), password.value)
            // ER-US-D02: back to the page that asked for login, never to an outside site.
            router.replace(safeRedirect(route.query.redirect))
        } catch (e) {
            formError.value = e.message
            verificationNeeded.value = e.code === 'EMAIL_NOT_VERIFIED'
            password.value = ''
        } finally {
            submitting.value = false
        }
    }
</script>

<style scoped>
    .narrow {
        max-width: 440px;
    }
    h1 {
        margin-top: 0;
    }
    .note { font-size: 0.9rem; margin: 14px 0 0; text-align: center; }
    .login-links { text-align: right; margin-top: 10px; font-size: .9rem; }
    .text-button { border: 0; background: none; color: var(--brand); text-decoration: underline; cursor: pointer; }
</style>
