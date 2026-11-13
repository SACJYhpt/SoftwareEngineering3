<template>
    <main class="page narrow">
        <form class="panel" novalidate @submit.prevent="onSubmit">
            <h1>登入</h1>
            <p v-if="route.query.expired" class="alert alert-info">登入已失效，請重新登入，登入後會回到原本的頁面。</p>
            <p v-else-if="route.query.redirect && route.query.redirect !== '/'" class="alert alert-info">請先登入，登入後會回到原本的頁面。</p>
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
            <!-- 帳密正確但尚未驗證信箱 (ER-US-A01、A03) -->
            <ResendVerification v-if="needsVerification" :email="email.trim()" />
            <button class="btn btn-large" type="submit" :disabled="submitting">{{ submitting ? '登入中…' : '登入' }}</button>
            <p class="links">
                <router-link to="/forgot-password">忘記密碼？</router-link>
                <router-link to="/register">還沒有帳號？立即註冊</router-link>
                <router-link to="/faq">常見問題</router-link>
            </p>
        </form>
    </main>
</template>

<script setup>
    import { reactive, ref } from 'vue'
    import { useRoute, useRouter } from 'vue-router'
    import { login } from '../auth'
    import { safeRedirect } from '../format'
    import ResendVerification from '../components/ResendVerification.vue'

    const route = useRoute()
    const router = useRouter()
    const email = ref('')
    const password = ref('')
    const errors = reactive({ email: '', password: '' })
    const formError = ref('')
    const submitting = ref(false)
    const needsVerification = ref(false)

    async function onSubmit() {
        errors.email = email.value.trim() ? '' : '請輸入信箱'
        errors.password = password.value ? '' : '請輸入密碼'
        formError.value = ''
        needsVerification.value = false
        if (errors.email || errors.password) return
        submitting.value = true
        try {
            await login(email.value.trim(), password.value)
            // ER-US-D02: back to the page that asked for login, never to an outside site.
            router.replace(safeRedirect(route.query.redirect))
        } catch (e) {
            formError.value = e.message
            needsVerification.value = e.code === 'EMAIL_NOT_VERIFIED'
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
    .links {
        display: flex;
        flex-wrap: wrap;
        justify-content: space-between;
        gap: 8px 16px;
        margin: 16px 0 0;
        font-size: 0.92rem;
    }
</style>
