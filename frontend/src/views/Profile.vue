<template>
    <main class="page narrow">
        <form class="panel" novalidate @submit.prevent="onSubmit">
            <h1>個人資料</h1>
            <p class="muted">修改系所與年級後，新的報名將以更新後的資料判斷資格；已成立的報名不受影響。</p>

            <p v-if="loadError" class="alert alert-error" role="alert">{{ loadError }}</p>

            <div class="field">
                <label for="profile-name">姓名</label>
                <input id="profile-name" :value="user?.name || ''" readonly disabled />
            </div>

            <div class="field">
                <label for="profile-email">學校信箱</label>
                <input id="profile-email" :value="user?.email || ''" readonly disabled />
            </div>

            <!-- 身分別不可自行修改 (ER-US-A10、ER-US-I07) -->
            <div class="field">
                <label for="profile-identity">身分別</label>
                <input id="profile-identity" :value="identityLabel" readonly disabled />
                <span class="hint">身分別不可自行修改，如需更正請聯絡系統管理員。</span>
            </div>

            <p v-if="!hasValidIdentity" class="alert alert-info" role="status">
                此帳號尚未設定身分別，如需更正請聯絡系統管理員。
            </p>

            <template v-else>
                <div :class="['field', { invalid: errors.department_id }]">
                    <label for="profile-department" class="required">{{ unitLabel }}</label>
                    <select id="profile-department" v-model="form.department_id" :disabled="loadingUnits || submitting"
                        @change="departmentInactiveNotice = ''">
                        <option disabled value="">{{ loadingUnits ? '載入中…' : '請選擇' }}</option>
                        <option v-for="unit in units" :key="unit.id" :value="unit.id">{{ unit.name }}</option>
                    </select>
                    <span v-if="departmentInactiveNotice" class="hint">{{ departmentInactiveNotice }}</span>
                    <span v-if="errors.department_id" class="error">{{ errors.department_id }}</span>
                </div>

                <div v-if="isStudent" :class="['field', { invalid: errors.grade }]">
                    <label for="profile-grade" class="required">年級</label>
                    <select id="profile-grade" v-model="form.grade" :disabled="submitting">
                        <option disabled value="">請選擇</option>
                        <option v-for="grade in GRADES" :key="grade.value" :value="grade.value">{{ grade.label }}</option>
                    </select>
                    <span v-if="errors.grade" class="error">{{ errors.grade }}</span>
                </div>

                <div v-if="formError" class="alert alert-error" role="alert">{{ formError }}</div>
                <div v-if="successMessage" class="alert alert-ok" role="status">{{ successMessage }}</div>

                <button class="btn btn-large" type="submit" :disabled="submitting || loadingUnits">
                    {{ submitting ? '儲存中…' : '儲存變更' }}
                </button>
            </template>
        </form>
    </main>
</template>

<script setup>
    import { computed, onMounted, reactive, ref } from 'vue'
    import { request } from '../api'
    import { auth, refreshUser } from '../auth'
    import { GRADES, IDENTITY_LABELS } from '../format'

    const user = computed(() => auth.user)
    const identity = computed(() => user.value?.identity || '')
    const hasValidIdentity = computed(() => ['student', 'teacher', 'staff'].includes(identity.value))
    const identityLabel = computed(() => IDENTITY_LABELS[identity.value] || '未設定')
    const isStudent = computed(() => identity.value === 'student')
    const unitKind = computed(() => (identity.value === 'staff' ? 'office' : 'department'))
    const unitLabel = computed(() => (unitKind.value === 'office' ? '行政單位' : '系所'))

    const form = reactive({
        department_id: user.value?.department?.id ?? '',
        grade: user.value?.grade ?? '',
    })
    const errors = reactive({ department_id: '', grade: '' })
    const units = ref([])
    const loadingUnits = ref(false)
    const loadError = ref('')
    const departmentInactiveNotice = ref('')
    const formError = ref('')
    const successMessage = ref('')
    const submitting = ref(false)

    const CODE_FIELDS = {
        DEPARTMENT_INVALID: 'department_id',
        GRADE_REQUIRED: 'grade',
    }

    function syncFromUser() {
        form.department_id = user.value?.department?.id ?? ''
        form.grade = isStudent.value ? (user.value?.grade ?? '') : ''
    }

    function validate() {
        errors.department_id = ''
        errors.grade = ''
        if (!form.department_id) errors.department_id = `請選擇${unitLabel.value}`
        if (isStudent.value && !form.grade) errors.grade = '學生須選擇年級'
        return !errors.department_id && !errors.grade
    }

    async function loadUnits() {
        if (!hasValidIdentity.value) return
        loadingUnits.value = true
        loadError.value = ''
        try {
            units.value = await request(`/units?kind=${unitKind.value}`)
            if (form.department_id && !units.value.some((u) => Number(u.id) === Number(form.department_id))) {
                form.department_id = ''
                departmentInactiveNotice.value = '原單位已停用，請重新選擇'
            } else {
                departmentInactiveNotice.value = ''
            }
        } catch (e) {
            loadError.value = `無法載入${unitLabel.value}清單：${e.message}`
        } finally {
            loadingUnits.value = false
        }
    }

    async function onSubmit() {
        formError.value = ''
        successMessage.value = ''
        if (!validate()) {
            formError.value = '請修正標示的欄位後再送出'
            return
        }
        submitting.value = true
        try {
            // Backend ProfileUpdate uses extra="forbid": only department_id and grade are allowed.
            const body = {
                department_id: Number(form.department_id),
                grade: isStudent.value ? Number(form.grade) : null,
            }
            await request('/me/profile', { method: 'PATCH', body })
            await refreshUser()
            syncFromUser()
            successMessage.value = '個人資料已更新。已成立的報名不受影響，新的報名將以更新後的資料判斷資格。'
        } catch (e) {
            Object.assign(errors, e.fieldErrors || {})
            if (CODE_FIELDS[e.code]) errors[CODE_FIELDS[e.code]] = e.message
            formError.value = e.message
        } finally {
            submitting.value = false
        }
    }

    onMounted(() => {
        syncFromUser()
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
</style>
