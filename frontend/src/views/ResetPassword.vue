<template>
    <main class="page narrow">
        <section v-if="done" class="panel">
            <h1>密碼已重設</h1>
            <p class="alert alert-ok">請使用新密碼登入。其他裝置上的登入已全部登出。</p>
            <router-link class="btn btn-large" to="/login">前往登入</router-link>
        </section>
        <section v-else-if="!token" class="panel">
            <h1>重設密碼</h1>
            <p class="alert alert-error">連結不完整，請直接開啟重設密碼信中的連結。</p>
            <router-link to="/forgot-password">重新申請重設連結</router-link>
        </section>
        <form v-else class="panel" novalidate @submit.prevent="onSubmit">
            <h1>重設密碼</h1>
            <div :class="['field', { invalid: errors.password }]">
                <label for="password" class="required">新密碼</label>
                <input id="password" v-model="password" type="password" autocomplete="new-password" />
                <span class="hint">至少 8 碼，且須同時包含英文字母與數字。</span>
                <span v-if="errors.password" class="error">{{ errors.password }}</span>
            </div>
            <div :class="['field', { invalid: errors.confirm }]">
                <label for="confirm" class="required">確認新密碼</label>
                <input id="confirm" v-model="confirm" type="password" autocomplete="new-password" />
                <span v-if="errors.confirm" class="error">{{ errors.confirm }}</span>
            </div>
            <template v-if="formError">
                <p class="alert alert-error" role="alert">{{ formError }}</p>
                <p v-if="linkInvalid"><router-link to="/forgot-password">重新申請重設連結</router-link></p>
            </template>
            <button class="btn btn-large" type="submit" :disabled="busy || linkInvalid">{{ busy ? '處理中…' : '確認重設密碼' }}</button>
        </form>
    </main>
</template>

<script setup>
    import { onBeforeUnmount, reactive, ref } from 'vue'
    import { request } from '../api'
    import { takeTokenFromHash } from '../format'

    const token = ref(takeTokenFromHash())
    const password = ref('')
    const confirm = ref('')
    const errors = reactive({ password: '', confirm: '' })
    const formError = ref('')
    const linkInvalid = ref(false)
    const busy = ref(false)
    const done = ref(false)

    async function onSubmit() {
        errors.password = password.value.length >= 8 && /[A-Za-z]/.test(password.value) && /[0-9]/.test(password.value)
            ? '' : '密碼至少 8 碼，且須同時包含英文字母與數字'
        errors.confirm = confirm.value === password.value ? '' : '兩次輸入的密碼不一致'
        formError.value = ''
        if (errors.password || errors.confirm) return
        busy.value = true
        try {
            await request('/auth/reset-password', { method: 'POST', body: { token: token.value, password: password.value }, withAuth: false })
            done.value = true
        } catch (e) {
            linkInvalid.value = e.code === 'LINK_INVALID'
            formError.value = linkInvalid.value ? '連結已失效（超過 1 小時或已使用過），請重新申請。' : e.message
        } finally {
            busy.value = false
        }
    }

    // A newer link opened in the same tab only changes the #hash.
    function onHashChange() {
        const next = takeTokenFromHash()
        if (!next) return
        token.value = next
        done.value = false
        linkInvalid.value = false
        formError.value = ''
    }
    window.addEventListener('hashchange', onHashChange)
    onBeforeUnmount(() => window.removeEventListener('hashchange', onHashChange))
</script>

<style scoped>
    .narrow {
        max-width: 480px;
    }
    h1 {
        margin-top: 0;
    }
</style>
