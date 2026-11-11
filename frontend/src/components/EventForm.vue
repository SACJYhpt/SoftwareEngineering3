<template>
    <!-- Fields shared by the create and edit event pages; the parent owns form, errors and submit. -->
    <fieldset>
        <legend>基本資訊</legend>
        <div :class="['field', { invalid: errors.unit_id }]">
            <label for="unit" class="required">主辦單位</label>
            <select id="unit" v-model="form.unit_id" :disabled="unitLocked">
                <option disabled value="">請選擇</option>
                <option v-for="unit in units" :key="unit.id" :value="unit.id">{{ unit.name }}</option>
            </select>
            <span v-if="unitLocked && editing" class="hint">活動建立後不能更改主辦單位。</span>
            <span v-if="errors.unit_id" class="error">{{ errors.unit_id }}</span>
        </div>
        <div :class="['field', { invalid: errors.name }]">
            <label for="name" class="required">活動名稱</label>
            <input id="name" v-model="form.name" maxlength="200" />
            <span v-if="errors.name" class="error">{{ errors.name }}</span>
        </div>
        <div :class="['field', { invalid: errors.type }]">
            <label for="type" class="required">活動類型</label>
            <select id="type" v-model="form.type">
                <option disabled value="">請選擇</option>
                <option v-for="item in typeOptions" :key="item.name" :value="item.name">{{ item.name }}</option>
            </select>
            <span v-if="errors.type" class="error">{{ errors.type }}</span>
        </div>
        <div :class="['field', { invalid: errors.description }]">
            <label for="description" class="required">活動描述</label>
            <textarea id="description" v-model="form.description"></textarea>
            <span v-if="errors.description" class="error">{{ errors.description }}</span>
        </div>
    </fieldset>

    <fieldset>
        <legend>時間與地點</legend>
        <div class="two-col">
            <div :class="['field', { invalid: errors.start_time }]">
                <label for="start" class="required">活動開始</label>
                <input id="start" v-model="form.start_time" type="datetime-local" />
                <span v-if="errors.start_time" class="error">{{ errors.start_time }}</span>
            </div>
            <div :class="['field', { invalid: errors.end_time }]">
                <label for="end" class="required">活動結束</label>
                <input id="end" v-model="form.end_time" type="datetime-local" />
                <span v-if="errors.end_time" class="error">{{ errors.end_time }}</span>
            </div>
        </div>
        <div :class="['field', { invalid: errors.location }]">
            <label for="location" class="required">地點</label>
            <input id="location" v-model="form.location" maxlength="255" />
            <span v-if="errors.location" class="error">{{ errors.location }}</span>
        </div>
        <div class="two-col">
            <div :class="['field', { invalid: errors.registration_start }]">
                <label for="reg-start" class="required">報名開始</label>
                <input id="reg-start" v-model="form.registration_start" type="datetime-local" />
                <span v-if="errors.registration_start" class="error">{{ errors.registration_start }}</span>
            </div>
            <div :class="['field', { invalid: errors.registration_deadline }]">
                <label for="reg-end" class="required">報名截止</label>
                <input id="reg-end" v-model="form.registration_deadline" type="datetime-local" />
                <span class="hint">截止時間當下起即不可報名，且不可晚於活動開始。</span>
                <span v-if="errors.registration_deadline" class="error">{{ errors.registration_deadline }}</span>
            </div>
        </div>
    </fieldset>

    <fieldset>
        <legend>報名規則與聯絡</legend>
        <div :class="['field', { invalid: errors.capacity }]">
            <label for="capacity">名額上限</label>
            <input id="capacity" v-model="form.capacity" type="number" min="1" step="1" inputmode="numeric" />
            <span class="hint">{{ editing ? '留空表示不限名額；不可低於目前已報名人數。' : '留空表示不限名額。' }}</span>
            <span v-if="errors.capacity" class="error">{{ errors.capacity }}</span>
        </div>
        <div :class="['field', { invalid: errors.contact_information }]">
            <label for="contact" class="required">聯絡方式</label>
            <input id="contact" v-model="form.contact_information" maxlength="255" placeholder="例如：活動窗口 Email 或分機" />
            <span v-if="errors.contact_information" class="error">{{ errors.contact_information }}</span>
        </div>
        <div class="field">
            <label for="notes">注意事項</label>
            <textarea id="notes" v-model="form.notes"></textarea>
        </div>
    </fieldset>
</template>

<script setup>
    import { computed } from 'vue'

    const props = defineProps({
        form: { type: Object, required: true },
        errors: { type: Object, required: true },
        units: { type: Array, required: true },
        types: { type: Array, required: true },
        unitLocked: { type: Boolean, default: false },
        editing: { type: Boolean, default: false },
    })

    // A disabled type stays selectable on events that already use it.
    const typeOptions = computed(() => {
        const options = props.types.slice()
        if (props.form.type && !options.some((item) => item.name === props.form.type)) {
            options.push({ name: props.form.type })
        }
        return options
    })
</script>

<style scoped>
    fieldset {
        border: none;
        border-top: 1px solid var(--border);
        margin: 20px 0 0;
        padding: 16px 0 0;
        min-width: 0;
    }
    legend {
        font-weight: 700;
        color: var(--brand);
        padding: 0 8px 0 0;
    }
    .two-col {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr));
        gap: 0 16px;
    }
</style>
