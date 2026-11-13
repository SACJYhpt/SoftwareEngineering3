<template>
    <main class="page narrow">
        <h1>主辦規範</h1>
        <p class="muted">活動管理者首次發布活動前，或規範更新後，須閱讀並確認目前版本。</p>
        <OrganizerTermsPanel @acknowledged="acknowledged = true" />
        <p v-if="acknowledged" class="next">
            <router-link class="btn" to="/events/new">建立活動</router-link>
            <router-link class="btn btn-outline" to="/manage">回到活動管理</router-link>
        </p>
    </main>
</template>

<script setup>
    import { ref } from 'vue'
    import OrganizerTermsPanel from '../components/OrganizerTermsPanel.vue'

    const acknowledged = ref(false)
</script>

<style scoped>
    .narrow {
        max-width: 760px;
    }
    h1 {
        margin-top: 0;
    }
    .next {
        display: flex;
        gap: 8px;
        margin-top: 16px;
    }
</style>
