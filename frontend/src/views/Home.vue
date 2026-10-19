<template>
    <main class="main-content">
        <header class="hero-banner">
            <h2>探索校園活動，豐富大學生活</h2>
            <p>尋找近期熱門的活動</p>
        </header>

        <div class="filter-tabs">
            <button class="tab active">即將開始</button>
            <button class="tab">熱門活動</button>
            <button class="tab">社團活動</button>
        </div>

        <div class="event-grid">
            <EventCard v-for="event in mockEvents" :key="event.id" :event="event" />
        </div>
    </main>
</template>

<script setup>
    import { ref } from 'vue'
    import EventCard from '../components/EventCard.vue'

    const mockEvents = ref([
        {
            id: 1,
            title: '知名先輩校友講座',
            time: '2026-08-10 11:45',
            location: '下北澤野獸邸',
            restriction: '無身分限制，可自由攜帶紅茶',
            capacity: 40,
            enrolled: 40,
            image: 'https://images.unsplash.com/photo-1496247749665-49cf5b1022e9?auto=format&fit=crop&w=400&q=80'
        },
        {
            id: 2,
            title: '軟體工程專案分享會',
            time: '2026-10-21 09:30',
            location: 'INS 203',
            restriction: '僅限【軟體工程】相關修課人員',
            capacity: 100,
            enrolled: 45,
            image: 'https://images.unsplash.com/photo-1544144433-d50aff500b91?auto=format&fit=crop&w=400&q=80'
        }
    ])
</script>

<style scoped>
    .main-content {
        max-width: 1200px;
        margin: 0 auto;
        padding: 24px;
    }
    .hero-banner {
        background-color: #004d99;
        color: white;
        padding: 48px 24px;
        border-radius: 8px;
        text-align: center;
        margin-bottom: 32px;
    }
    .filter-tabs {
        display: flex;
        gap: 16px;
        margin-bottom: 24px;
        border-bottom: 1px solid #ddd;
        padding-bottom: 8px;
        justify-content: center;
    }
    .tab {
        background: none;
        border: none;
        font-size: 1rem;
        color: #666;
        cursor: pointer;
        padding: 8px 0;
    }
    .tab.active {
        color: #004d99;
        font-weight: bold;
        border-bottom: 2px solid #004d99;
    }
    .event-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
        gap: 24px;
    }
</style>