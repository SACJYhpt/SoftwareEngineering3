<template>
    <section>
        <!-- 依姓名、Email、系所搜尋，可再依單位與角色篩選 (ER-US-I01、I12) -->
        <form class="panel search" @submit.prevent="search(1)">
            <label class="grow">
                關鍵字
                <input v-model.trim="filters.q" type="search" maxlength="200" placeholder="姓名、Email 或系所 (可部分比對)" />
            </label>
            <label>
                單位
                <select v-model="filters.unit_id">
                    <option value="">全部單位</option>
                    <option v-for="unit in units" :key="unit.id" :value="unit.id">{{ unit.name }}{{ unit.is_active ? '' : '（停用）' }}</option>
                </select>
            </label>
            <label>
                角色
                <select v-model="filters.role">
                    <option value="">全部角色</option>
                    <option v-for="(label, key) in ROLE_LABELS" :key="key" :value="key">{{ label }}</option>
                </select>
            </label>
            <button class="btn" type="submit">搜尋</button>
        </form>

        <p v-if="message" :class="['alert', message.ok ? 'alert-ok' : 'alert-error']" role="status">{{ message.text }}</p>
        <p v-if="loading" class="muted">載入中…</p>
        <p v-else-if="error" class="alert alert-error">{{ error }}</p>
        <template v-else>
            <p class="muted">共 {{ result.total }} 位使用者</p>
            <div class="table-wrap">
                <table class="table">
                    <thead>
                        <tr><th>姓名</th><th>Email</th><th>身分別</th><th>系所</th><th>角色</th><th>管理的單位 (ER-US-I02)</th></tr>
                    </thead>
                    <tbody>
                        <tr v-for="user in result.items" :key="user.id">
                            <td>{{ user.name }}</td>
                            <td>{{ user.email }}</td>
                            <td>{{ IDENTITY_LABELS[user.identity] || '—' }}</td>
                            <td>{{ user.department ? user.department.name : '—' }}</td>
                            <td>{{ ROLE_LABELS[user.role] }}</td>
                            <td>
                                <span v-if="user.role === 'admin'" class="muted">系統管理員不可透過此處變更</span>
                                <template v-else>
                                    <span v-for="unit in user.managed_units" :key="unit.id" class="chip">
                                        {{ unit.name }}
                                        <button type="button" :aria-label="`取消 ${unit.name} 的管理資格`" :disabled="busy" @click="revoke(user, unit)">✕</button>
                                    </span>
                                    <span class="assign">
                                        <select v-model="assignChoice[user.id]" :aria-label="`指派 ${user.name} 管理的單位`">
                                            <option value="">指派單位…</option>
                                            <option v-for="unit in assignable(user)" :key="unit.id" :value="unit.id">{{ unit.name }}</option>
                                        </select>
                                        <button class="btn btn-outline btn-small" type="button" :disabled="!assignChoice[user.id] || busy" @click="assign(user)">指派</button>
                                    </span>
                                </template>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
            <div class="pager">
                <button class="btn btn-outline btn-small" :disabled="page <= 1" @click="search(page - 1)">上一頁</button>
                <span>第 {{ page }} / {{ pages }} 頁</span>
                <button class="btn btn-outline btn-small" :disabled="page >= pages" @click="search(page + 1)">下一頁</button>
            </div>
        </template>
    </section>
</template>

<script setup>
    import { computed, onMounted, reactive, ref } from 'vue'
    import { request } from '../../api'
    import { IDENTITY_LABELS, ROLE_LABELS } from '../../format'

    const PAGE_SIZE = 20
    const filters = reactive({ q: '', unit_id: '', role: '' })
    const units = ref([])
    const result = ref({ items: [], total: 0 })
    const page = ref(1)
    const loading = ref(true)
    const error = ref('')
    const message = ref(null)
    const busy = ref(false)
    const assignChoice = reactive({})

    const pages = computed(() => Math.max(1, Math.ceil(result.value.total / PAGE_SIZE)))

    function assignable(user) {
        const held = new Set(user.managed_units.map((unit) => unit.id))
        return units.value.filter((unit) => unit.is_active && !held.has(unit.id))
    }

    async function search(target = page.value) {
        loading.value = true
        error.value = ''
        try {
            const params = new URLSearchParams({ page: target, page_size: PAGE_SIZE })
            for (const [key, value] of Object.entries(filters)) {
                if (value) params.set(key, value)
            }
            result.value = await request(`/admin/users?${params}`)
            page.value = target
        } catch (e) {
            error.value = e.message
        } finally {
            loading.value = false
        }
    }

    // Grants take effect on the user's next request (ER-US-I02).
    async function change(user, unit, assignIt) {
        const verb = assignIt ? '指派' : '取消'
        if (!window.confirm(`確定要${verb}「${user.name}」為「${unit.name}」的活動管理者嗎？`)) return
        busy.value = true
        message.value = null
        try {
            await request(`/admin/units/${unit.id}/managers/${user.id}`, { method: assignIt ? 'PUT' : 'DELETE' })
            message.value = { ok: true, text: `已${verb}「${user.name}」在「${unit.name}」的管理資格，下次操作時生效。` }
            assignChoice[user.id] = ''
            await search()
        } catch (e) {
            message.value = { ok: false, text: e.message }
        } finally {
            busy.value = false
        }
    }

    function assign(user) {
        const unit = units.value.find((item) => item.id === assignChoice[user.id])
        if (unit) change(user, unit, true)
    }

    function revoke(user, unit) {
        change(user, unit, false)
    }

    onMounted(async () => {
        try {
            units.value = await request('/admin/units')
        } catch (e) {
            error.value = e.message
        }
        await search(1)
    })
</script>

<style scoped>
    .search {
        display: flex;
        flex-wrap: wrap;
        align-items: end;
        gap: 12px;
        padding: 16px;
        margin-bottom: 16px;
    }
    .search label {
        display: grid;
        gap: 4px;
        font-weight: 600;
        font-size: 0.9rem;
    }
    .search .grow {
        flex: 1 1 240px;
    }
    .search input,
    .search select,
    .assign select {
        padding: 8px 10px;
        border: 1px solid var(--border);
        border-radius: 6px;
        background: #fff;
        min-width: 0;
    }
    .chip {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        margin: 0 6px 6px 0;
        padding: 2px 4px 2px 10px;
        border-radius: 999px;
        background: var(--info-bg);
        color: var(--info);
        font-size: 0.88rem;
    }
    .chip button {
        border: none;
        background: none;
        color: inherit;
        cursor: pointer;
    }
    .assign {
        display: inline-flex;
        gap: 6px;
    }
    .pager {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 12px;
        margin-top: 12px;
    }
</style>
