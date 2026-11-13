<template>
    <main class="page narrow">
        <div v-if="registeredEmail" class="panel">
            <h1>註冊成功</h1>
            <p class="alert alert-ok">驗證信已寄到 <strong>{{ registeredEmail }}</strong>，請在 24 小時內開啟信中的連結完成驗證，之後才能登入。</p>
            <ResendVerification :email="registeredEmail" prompt="沒有收到驗證信？" />
            <router-link to="/login" class="btn btn-large">前往登入</router-link>
        </div>

        <form v-else class="panel" novalidate @submit.prevent="onSubmit">
            <h1>建立帳號</h1>
            <p class="muted">只接受學校信箱。註冊後須完成信箱驗證才能登入。<router-link to="/faq">常見問題</router-link></p>

            <div :class="['field', { invalid: errors.email }]">
                <label for="email" class="required">學校信箱</label>
                <input id="email" v-model.trim="form.email" type="email" autocomplete="email" />
                <span v-if="errors.email" class="error">{{ errors.email }}</span>
            </div>
            <div :class="['field', { invalid: errors.name }]">
                <label for="name" class="required">姓名</label>
                <input id="name" v-model.trim="form.name" maxlength="100" autocomplete="name" />
                <span v-if="errors.name" class="error">{{ errors.name }}</span>
            </div>
            <div :class="['field', { invalid: errors.identity }]">
                <label for="identity" class="required">身分別</label>
                <select id="identity" v-model="form.identity">
                    <option disabled value="">請選擇</option>
                    <option v-for="(label, key) in IDENTITY_LABELS" :key="key" :value="key">{{ label }}</option>
                </select>
                <span class="hint">身分別註冊後無法自行修改，請確認選擇正確；如需更正請聯絡系統管理員。</span>
                <span v-if="errors.identity" class="error">{{ errors.identity }}</span>
            </div>
            <!-- 學生與教師選系所；行政人員選行政單位 -->
            <div :class="['field', { invalid: errors.department_id }]">
                <label for="department" class="required">{{ unitLabel }}</label>
                <select id="department" v-model="form.department_id" :disabled="!form.identity">
                    <option disabled value="">{{ form.identity ? '請選擇' : '請先選擇身分別' }}</option>
                    <option v-for="unit in units" :key="unit.id" :value="unit.id">{{ unit.name }}</option>
                </select>
                <span v-if="errors.department_id" class="error">{{ errors.department_id }}</span>
            </div>
            <div v-if="form.identity === 'student'" :class="['field', { invalid: errors.grade }]">
                <label for="grade" class="required">年級</label>
                <select id="grade" v-model="form.grade">
                    <option disabled value="">請選擇</option>
                    <option v-for="grade in GRADES" :key="grade.value" :value="grade.value">{{ grade.label }}</option>
                </select>
                <span v-if="errors.grade" class="error">{{ errors.grade }}</span>
            </div>
            <div :class="['field', { invalid: errors.password }]">
                <label for="password" class="required">密碼</label>
                <input id="password" v-model="form.password" type="password" autocomplete="new-password" />
                <span class="hint">至少 8 碼，且須同時包含英文字母與數字。</span>
                <span v-if="errors.password" class="error">{{ errors.password }}</span>
            </div>
            <div :class="['field', { invalid: errors.confirm }]">
                <label for="confirm" class="required">確認密碼</label>
                <input id="confirm" v-model="confirm" type="password" autocomplete="new-password" />
                <span v-if="errors.confirm" class="error">{{ errors.confirm }}</span>
            </div>

            <!-- 個資蒐集告知與同意，送出時附上告知版本 (ER-US-A02) -->
            <section :class="['notice', { invalid: errors.consent }]">
                <h2>個人資料蒐集告知<span v-if="notice">（第 {{ notice.version }} 版）</span></h2>
                <p v-if="noticeError" class="alert alert-error">{{ noticeError }}</p>
                <div v-else-if="notice" class="notice-text">{{ notice.content }}</div>
                <label class="consent">
                    <input v-model="form.consent" type="checkbox" :disabled="!notice" />
                    我已閱讀並同意上述個人資料蒐集告知事項
                </label>
                <span v-if="errors.consent" class="error">{{ errors.consent }}</span>
            </section>

            <div v-if="formError" class="alert alert-error" role="alert">{{ formError }}</div>
            <button class="btn btn-large" type="submit" :disabled="submitting || !notice">{{ submitting ? '註冊中…' : '註冊' }}</button>
            <p class="muted note">已經有帳號？<router-link to="/login">前往登入</router-link></p>
        </form>
    </main>
</template>

<script setup>
    import { computed, onMounted, reactive, ref, watch } from 'vue'
    import { request } from '../api'
    import { IDENTITY_LABELS } from '../format'
    import ResendVerification from '../components/ResendVerification.vue'

    const GRADES = [1, 2, 3, 4].map((n) => ({ value: n, label: `大學部 ${n} 年級` }))
        .concat([5, 6, 7].map((n) => ({ value: n, label: `研究所 ${n - 4} 年級` })))
    const FIELDS = ['email', 'name', 'identity', 'department_id', 'grade', 'password', 'confirm', 'consent']

    const form = reactive({ email: '', name: '', identity: '', department_id: '', grade: '', password: '', consent: false })
    const confirm = ref('')
    const errors = reactive(Object.fromEntries(FIELDS.map((field) => [field, ''])))
    const units = ref([])
    const notice = ref(null)
    const noticeError = ref('')
    const formError = ref('')
    const submitting = ref(false)
    const registeredEmail = ref('')

    // Students and teachers belong to a 系所; administrative staff to a 行政單位.
    const unitKind = computed(() => (form.identity === 'staff' ? 'office' : 'department'))
    const unitLabel = computed(() => (unitKind.value === 'office' ? '行政單位' : '系所'))

    async function loadUnits() {
        try {
            units.value = await request(`/units?kind=${unitKind.value}`, { withAuth: false })
        } catch (e) {
            formError.value = `無法載入${unitLabel.value}清單：` + e.message
        }
    }

    watch(() => form.identity, (identity, previous) => {
        if (identity !== 'student') form.grade = ''
        // Switching between staff and the other identities changes the list, so the choice is cleared.
        if ((identity === 'staff') !== (previous === 'staff')) {
            form.department_id = ''
            loadUnits()
        }
    })

    function validate() {
        for (const field of FIELDS) errors[field] = ''
        if (!form.email) errors.email = '請輸入學校信箱'
        if (!form.name) errors.name = '請輸入姓名'
        if (!form.identity) errors.identity = '請選擇身分別'
        if (!form.department_id) errors.department_id = `請選擇${unitLabel.value}`
        if (form.identity === 'student' && !form.grade) errors.grade = '學生須選擇年級'
        if (form.password.length < 8 || !/[A-Za-z]/.test(form.password) || !/[0-9]/.test(form.password)) {
            errors.password = '密碼至少 8 碼，且須同時包含英文字母與數字'
        }
        if (confirm.value !== form.password) errors.confirm = '兩次輸入的密碼不一致'
        if (!form.consent) errors.consent = '須同意個資告知事項才能註冊'
        return FIELDS.every((field) => !errors[field])
    }

    const CODE_FIELDS = {
        SCHOOL_EMAIL_REQUIRED: 'email', EMAIL_ALREADY_REGISTERED: 'email',
        DEPARTMENT_INVALID: 'department_id', PRIVACY_CONSENT_REQUIRED: 'consent',
    }

    async function loadNotice() {
        try {
            notice.value = await request('/privacy-notice', { withAuth: false })
            noticeError.value = ''
        } catch (e) {
            noticeError.value = '無法載入個資告知事項：' + e.message
        }
    }

    async function onSubmit() {
        formError.value = ''
        if (!validate()) {
            formError.value = '請修正標示的欄位後再送出'
            return
        }
        submitting.value = true
        try {
            await request('/auth/register', {
                method: 'POST', withAuth: false,
                body: {
                    email: form.email, name: form.name, identity: form.identity,
                    department_id: Number(form.department_id),
                    grade: form.identity === 'student' ? Number(form.grade) : null,
                    password: form.password, consent: form.consent, privacy_version: notice.value.version,
                },
            })
            registeredEmail.value = form.email.toLowerCase()
        } catch (e) {
            Object.assign(errors, e.fieldErrors || {})
            if (CODE_FIELDS[e.code]) errors[CODE_FIELDS[e.code]] = e.message
            if (e.code === 'PRIVACY_NOTICE_OUTDATED') {
                // The notice changed while the form was open: show the new one and ask again.
                form.consent = false
                await loadNotice()
            }
            formError.value = e.message
        } finally {
            submitting.value = false
        }
    }

    onMounted(() => {
        loadNotice()
        loadUnits()
    })
</script>

<style scoped>
    .narrow {
        max-width: 560px;
    }
    h1 {
        margin-top: 0;
    }
    .notice {
        margin: 8px 0 16px;
    }
    .notice h2 {
        font-size: 1.05rem;
        margin: 0 0 8px;
    }
    .notice-text {
        max-height: 220px;
        overflow-y: auto;
        white-space: pre-line;
        padding: 12px;
        border: 1px solid var(--border);
        border-radius: 6px;
        background: var(--bg);
        font-size: 0.92rem;
    }
    .notice.invalid .notice-text {
        border-color: var(--danger);
    }
    .consent {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        margin-top: 10px;
        font-weight: 600;
    }
    .consent input {
        margin-top: 5px;
    }
    .notice .error {
        color: var(--danger);
        font-size: 0.9rem;
    }
    .note {
        text-align: center;
        margin: 14px 0 0;
    }
</style>
