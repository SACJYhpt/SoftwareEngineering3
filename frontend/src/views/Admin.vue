<template>
    <main class="page">
        <h1>系統管理</h1>
        <div class="tabs" role="tablist">
            <button v-for="item in TABS" :key="item.key" role="tab" :aria-selected="tab === item.key"
                    :class="{ active: tab === item.key }" @click="tab = item.key">
                {{ item.label }}
            </button>
        </div>
        <component :is="current" />
    </main>
</template>

<script setup>
    import { computed, ref } from 'vue'
    import AdminUsers from '../components/admin/AdminUsers.vue'
    import AdminUnits from '../components/admin/AdminUnits.vue'
    import AdminEventTypes from '../components/admin/AdminEventTypes.vue'
    import AdminDocuments from '../components/admin/AdminDocuments.vue'
    import AdminEmails from '../components/admin/AdminEmails.vue'
    import AdminBackups from '../components/admin/AdminBackups.vue'

    const TABS = [
        { key: 'users', label: '使用者與權限', component: AdminUsers }, // ER-US-I01、I02、I12
        { key: 'units', label: '單位', component: AdminUnits }, // ER-US-I06
        { key: 'types', label: '活動類型', component: AdminEventTypes }, // ER-US-I05
        { key: 'documents', label: '公告文件', component: AdminDocuments }, // ER-US-A02、B17、I16
        { key: 'emails', label: '寄信紀錄', component: AdminEmails }, // ER-US-J02
        { key: 'backups', label: '備份', component: AdminBackups }, // ER-US-J03
    ]
    const tab = ref('users')
    const current = computed(() => TABS.find((item) => item.key === tab.value).component)
</script>

<style scoped>
    h1 {
        margin-top: 0;
    }
</style>
