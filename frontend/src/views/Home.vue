<template>
    <main class="page">
        <header class="hero-banner">
            <h1>探索校園活動，豐富大學生活</h1>
            <p>依開始時間列出即將舉行的活動</p>
        </header>

        <p v-if="loading" class="muted">載入中…</p>
        <div v-else-if="error" class="alert alert-error">
            {{ error }} <button class="btn btn-outline" @click="load">重新載入</button>
        </div>
        <p v-else-if="events.length === 0" class="muted empty">目前沒有即將舉行的活動。</p>
        <div v-else class="event-grid">
            <EventCard v-for="event in events" :key="event.id" :event="event" />
        </div>
    </main>
</template>

<script setup>
    import { onMounted, ref } from 'vue'
    import { request } from '../api'
    import EventCard from '../components/EventCard.vue'

    const events = ref([])
    const loading = ref(true)
    const error = ref('')

    async function load() {
        loading.value = true
        error.value = ''
        try {
            events.value = await request('/events')
        } catch (e) {
            error.value = e.message
        } finally {
            loading.value = false
        }
    }

    onMounted(load)
</script>

<style scoped>
    .hero-banner {
        background-color: var(--brand);
        color: white;
        padding: 36px 20px;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 28px;
    }
    .hero-banner h1 {
        color: white;
        margin: 0 0 8px;
        font-size: clamp(1.4rem, 4vw, 2rem);
    }
    .hero-banner p {
        margin: 0;
        opacity: 0.9;
    }
    .event-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr));
        gap: 20px;
    }
    .empty {
        text-align: center;
        padding: 40px 0;
    }
</style>
