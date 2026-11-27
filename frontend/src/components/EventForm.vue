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
        <!-- 候補設定 (ER-US-C07)：不限名額時無法開啟；開啟後預設為名額上限的一半（無條件進位） -->
        <div :class="['field', { invalid: errors.waitlist_enabled }]">
            <label class="checkbox-row" for="waitlist-enabled">
                <input id="waitlist-enabled" v-model="form.waitlist_enabled" type="checkbox" :disabled="!hasValidCapacity" />
                <span>開放候補</span>
            </label>
            <span class="hint">
                {{ hasValidCapacity ? '額滿後開放候補，有人取消時依先到先補自動遞補，不需本人確認。' : '不限名額的活動不會額滿，無法開啟候補。' }}
            </span>
            <span v-if="errors.waitlist_enabled" class="error">{{ errors.waitlist_enabled }}</span>
        </div>
        <div v-if="form.waitlist_enabled" :class="['field', { invalid: errors.waitlist_capacity }]">
            <label for="waitlist-capacity" class="required">候補人數上限</label>
            <input id="waitlist-capacity" v-model="form.waitlist_capacity" type="number" min="1" step="1" inputmode="numeric"
                @input="onWaitlistCapacityInput" />
            <span class="hint">
                {{ editing ? '預設為名額上限的一半（無條件進位）；不可低於目前候補人數。' : '預設為名額上限的一半（無條件進位），可調整為其他正整數。' }}
            </span>
            <span v-if="errors.waitlist_capacity" class="error">{{ errors.waitlist_capacity }}</span>
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

    <!-- 報名資格限制 (ER-US-C08)：三種條件皆可複選，未設定時所有一般使用者皆可報名 -->
    <fieldset>
        <legend>報名資格限制</legend>
        <p class="hint eligibility-hint">選填。未勾選任何條件表示不限；三種條件可複選，每種條件可選多個值。</p>

        <div :class="['field', { invalid: errors.eligibility_identities }]">
            <span class="group-label">身分別</span>
            <div class="checkbox-grid">
                <label v-for="(label, key) in IDENTITY_LABELS" :key="key" class="checkbox-option">
                    <input v-model="form.eligibility_identities" type="checkbox" :value="key" />
                    <span>{{ label }}</span>
                </label>
            </div>
            <span v-if="errors.eligibility_identities" class="error">{{ errors.eligibility_identities }}</span>
        </div>

        <div :class="['field', { invalid: errors.eligibility_department_ids }]">
            <span class="group-label">系所／行政單位</span>
            <div v-if="departments.length" class="unit-group">
                <span class="subgroup-label">系所</span>
                <div class="checkbox-grid">
                    <label v-for="unit in departments" :key="unit.id" class="checkbox-option">
                        <input v-model="form.eligibility_department_ids" type="checkbox" :value="unit.id" />
                        <span>{{ unit.name }}</span>
                    </label>
                </div>
            </div>
            <div v-if="offices.length" class="unit-group">
                <span class="subgroup-label">行政單位</span>
                <div class="checkbox-grid">
                    <label v-for="unit in offices" :key="unit.id" class="checkbox-option">
                        <input v-model="form.eligibility_department_ids" type="checkbox" :value="unit.id" />
                        <span>{{ unit.name }}</span>
                    </label>
                </div>
            </div>
            <div v-if="inactiveDepartmentIds.length" class="unit-group">
                <span class="subgroup-label">已停用單位（請取消勾選後再儲存）</span>
                <div class="checkbox-grid">
                    <label v-for="unitId in inactiveDepartmentIds" :key="unitId" class="checkbox-option">
                        <input v-model="form.eligibility_department_ids" type="checkbox" :value="unitId" />
                        <span>已停用單位（ID: {{ unitId }}）</span>
                    </label>
                </div>
            </div>
            <span v-if="!departments.length && !offices.length && !inactiveDepartmentIds.length" class="hint">尚無可選的系所或行政單位。</span>
            <span v-if="errors.eligibility_department_ids" class="error">{{ errors.eligibility_department_ids }}</span>
        </div>

        <div :class="['field', { invalid: errors.eligibility_grades }]">
            <span class="group-label">年級</span>
            <div class="checkbox-grid">
                <label v-for="grade in GRADES" :key="grade.value" class="checkbox-option">
                    <input v-model="form.eligibility_grades" type="checkbox" :value="grade.value" />
                    <span>{{ grade.label }}</span>
                </label>
            </div>
            <span v-if="errors.eligibility_grades" class="error">{{ errors.eligibility_grades }}</span>
        </div>
    </fieldset>
</template>

<script setup>
    import { computed, ref, watch } from 'vue'
    import { defaultWaitlistCapacity, isPositiveInt } from '../eventForm'
    import { GRADES, IDENTITY_LABELS } from '../format'

    const props = defineProps({
        form: { type: Object, required: true },
        errors: { type: Object, required: true },
        units: { type: Array, required: true },
        types: { type: Array, required: true },
        departments: { type: Array, default: () => [] },
        offices: { type: Array, default: () => [] },
        unitLocked: { type: Boolean, default: false },
        editing: { type: Boolean, default: false },
    })

    const hasValidCapacity = computed(() => isPositiveInt(props.form.capacity))
    const activeUnitIds = computed(() => new Set([
        ...props.departments.map((unit) => Number(unit.id)),
        ...props.offices.map((unit) => Number(unit.id)),
    ]))
    const inactiveDepartmentIds = computed(() => {
        const selected = Array.isArray(props.form.eligibility_department_ids) ? props.form.eligibility_department_ids : []
        return selected.map(Number).filter((id) => Number.isInteger(id) && id > 0 && !activeUnitIds.value.has(id))
    })

    // L1: in edit mode, treat an existing saved waitlist_capacity as customized so capacity edits don't overwrite it.
    const waitlistCapacityCustomized = ref(
        Boolean(props.editing && props.form.waitlist_enabled && String(props.form.waitlist_capacity).trim() !== '')
    )
    // M1: stash previous waitlist_capacity when unchecked so re-checking restores it.
    const savedWaitlistCapacity = ref('')

    function onWaitlistCapacityInput() {
        waitlistCapacityCustomized.value = String(props.form.waitlist_capacity).trim() !== ''
    }

    watch(() => props.form.capacity, (newCapacity, oldCapacity) => {
        if (!isPositiveInt(newCapacity)) {
            const current = String(props.form.waitlist_capacity).trim()
            if (current !== '') savedWaitlistCapacity.value = current
            props.form.waitlist_enabled = false
            props.form.waitlist_capacity = ''
            waitlistCapacityCustomized.value = false
            props.errors.waitlist_enabled = ''
            props.errors.waitlist_capacity = ''
            return
        }
        if (props.form.waitlist_enabled && !waitlistCapacityCustomized.value) {
            const current = String(props.form.waitlist_capacity).trim()
            if (current === '' || current === defaultWaitlistCapacity(oldCapacity)) {
                props.form.waitlist_capacity = defaultWaitlistCapacity(newCapacity)
            }
        }
    })

    watch(() => props.form.waitlist_enabled, (enabled) => {
        if (!enabled) {
            const current = String(props.form.waitlist_capacity).trim()
            if (current !== '') savedWaitlistCapacity.value = current
            props.form.waitlist_capacity = ''
            waitlistCapacityCustomized.value = false
            props.errors.waitlist_enabled = ''
            props.errors.waitlist_capacity = ''
            return
        }
        if (!hasValidCapacity.value) {
            props.form.waitlist_enabled = false
            props.form.waitlist_capacity = ''
            return
        }
        if (String(props.form.waitlist_capacity).trim() === '') {
            if (savedWaitlistCapacity.value !== '') {
                props.form.waitlist_capacity = savedWaitlistCapacity.value
                waitlistCapacityCustomized.value = true
            } else {
                props.form.waitlist_capacity = defaultWaitlistCapacity(props.form.capacity)
                waitlistCapacityCustomized.value = false
            }
        }
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
    .checkbox-row {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        font-weight: 600;
        cursor: pointer;
    }
    .checkbox-row input {
        width: auto;
        margin: 0;
    }
    .eligibility-hint {
        margin: 0 0 12px;
    }
    .group-label {
        display: block;
        font-weight: 600;
        margin-bottom: 6px;
    }
    .unit-group {
        margin-bottom: 10px;
    }
    .subgroup-label {
        display: block;
        font-size: 0.9rem;
        color: var(--muted);
        margin-bottom: 4px;
    }
    .checkbox-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
        gap: 6px 12px;
    }
    .checkbox-option {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-weight: 400;
        cursor: pointer;
    }
    .checkbox-option input {
        width: auto;
        margin: 0;
    }
</style>
