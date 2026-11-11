<template>
    <!-- 新增、更名、停用；已被使用的項目不能刪除，只能停用 -->
    <section>
        <form class="panel add" @submit.prevent="create">
            <label class="grow">
                新增{{ noun }}
                <input v-model.trim="draft.name" maxlength="100" :placeholder="`${noun}名稱`" />
            </label>
            <label v-if="withKind">
                類型
                <select v-model="draft.kind">
                    <option v-for="(label, key) in UNIT_KIND_LABELS" :key="key" :value="key">{{ label }}</option>
                </select>
            </label>
            <button class="btn" type="submit" :disabled="busy || !draft.name">新增</button>
        </form>

        <p v-if="message" :class="['alert', message.ok ? 'alert-ok' : 'alert-error']" role="status">{{ message.text }}</p>
        <p v-if="loading" class="muted">載入中…</p>
        <div v-else class="table-wrap">
            <table class="table">
                <thead>
                    <tr><th>名稱</th><th v-if="withKind">類型</th><th>狀態</th><th>操作</th></tr>
                </thead>
                <tbody>
                    <tr v-for="item in items" :key="item.id">
                        <template v-if="editing && editing.id === item.id">
                            <td><input v-model.trim="editing.name" maxlength="100" :aria-label="`${noun}名稱`" /></td>
                            <td v-if="withKind">
                                <select v-model="editing.kind" aria-label="類型">
                                    <option v-for="(label, key) in UNIT_KIND_LABELS" :key="key" :value="key">{{ label }}</option>
                                </select>
                            </td>
                            <td>
                                <label class="check"><input v-model="editing.is_active" type="checkbox" /> 啟用</label>
                            </td>
                            <td class="ops">
                                <button class="btn btn-small" type="button" :disabled="busy || !editing.name" @click="save">儲存</button>
                                <button class="btn btn-outline btn-small" type="button" @click="editing = null">取消</button>
                            </td>
                        </template>
                        <template v-else>
                            <td>{{ item.name }}</td>
                            <td v-if="withKind">{{ UNIT_KIND_LABELS[item.kind] }}</td>
                            <td><span :class="['badge', item.is_active ? 'badge-ok' : 'badge-muted']">{{ item.is_active ? '啟用' : '停用' }}</span></td>
                            <td class="ops">
                                <button class="btn btn-outline btn-small" type="button" @click="editing = { ...item }">編輯</button>
                                <button class="btn btn-outline btn-small" type="button" :disabled="busy" @click="toggle(item)">{{ item.is_active ? '停用' : '啟用' }}</button>
                                <button class="btn btn-outline btn-small" type="button" :disabled="busy" @click="remove(item)">刪除</button>
                            </td>
                        </template>
                    </tr>
                </tbody>
            </table>
        </div>
        <p class="muted small">{{ hint }}</p>
    </section>
</template>

<script setup>
    import { onMounted, reactive, ref } from 'vue'
    import { request } from '../../api'
    import { UNIT_KIND_LABELS } from '../../format'

    const props = defineProps({
        endpoint: { type: String, required: true }, // /admin/units or /admin/event-types
        noun: { type: String, required: true },
        withKind: { type: Boolean, default: false },
        hint: { type: String, default: '' },
    })

    const items = ref([])
    const loading = ref(true)
    const busy = ref(false)
    const message = ref(null)
    const editing = ref(null)
    const draft = reactive({ name: '', kind: 'department' })

    function body(item) {
        const data = { name: item.name, is_active: item.is_active }
        if (props.withKind) data.kind = item.kind
        return data
    }

    async function load() {
        try {
            items.value = await request(props.endpoint)
        } catch (e) {
            message.value = { ok: false, text: e.message }
        } finally {
            loading.value = false
        }
    }

    async function run(action, success) {
        busy.value = true
        message.value = null
        try {
            await action()
            message.value = { ok: true, text: success }
            await load()
            return true
        } catch (e) {
            message.value = { ok: false, text: e.message }
            return false
        } finally {
            busy.value = false
        }
    }

    async function create() {
        const item = { name: draft.name, kind: draft.kind, is_active: true }
        if (await run(() => request(props.endpoint, { method: 'POST', body: body(item) }), `已新增「${draft.name}」`)) {
            draft.name = ''
        }
    }

    async function save() {
        const item = editing.value
        if (await run(() => request(`${props.endpoint}/${item.id}`, { method: 'PUT', body: body(item) }), `已更新「${item.name}」`)) {
            editing.value = null
        }
    }

    function toggle(item) {
        const next = { ...item, is_active: !item.is_active }
        run(() => request(`${props.endpoint}/${item.id}`, { method: 'PUT', body: body(next) }),
            `已${next.is_active ? '啟用' : '停用'}「${item.name}」`)
    }

    function remove(item) {
        if (!window.confirm(`確定要刪除「${item.name}」嗎？已被使用的${props.noun}無法刪除，只能停用。`)) return
        run(() => request(`${props.endpoint}/${item.id}`, { method: 'DELETE' }), `已刪除「${item.name}」`)
    }

    onMounted(load)
</script>

<style scoped>
    .add {
        display: flex;
        flex-wrap: wrap;
        align-items: end;
        gap: 12px;
        padding: 16px;
        margin-bottom: 16px;
    }
    .add label {
        display: grid;
        gap: 4px;
        font-weight: 600;
        font-size: 0.9rem;
    }
    .add .grow {
        flex: 1 1 220px;
    }
    input,
    select {
        padding: 7px 10px;
        border: 1px solid var(--border);
        border-radius: 6px;
        background: #fff;
        min-width: 0;
    }
    .check {
        display: inline-flex;
        gap: 6px;
        align-items: center;
    }
    .ops {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
    }
    .small {
        font-size: 0.88rem;
    }
</style>
