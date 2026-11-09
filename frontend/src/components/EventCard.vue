<template>
    <router-link :to="`/events/${event.id}`" class="event-card-link">
        <article class="event-card">
            <!-- 封面圖片 (ER-US-C06) 尚未排定，先以預設封面顯示活動類型 -->
            <div class="card-cover" aria-hidden="true">{{ event.type }}</div>
            <div class="card-content">
                <div class="card-top">
                    <span :class="['badge', 'badge-' + (STATUS_TONE[event.status] || 'muted')]">{{ event.status }}</span>
                    <span v-if="event.my_registration_status === '已報名'" class="badge badge-ok">已報名</span>
                </div>
                <h3 class="card-title">{{ event.name }}</h3>
                <p class="card-info">📅 {{ formatDateTime(event.start_time) }}</p>
                <p class="card-info">📍 {{ event.location }}</p>
                <p class="card-info">🏫 {{ event.unit.name }}</p>
                <p class="card-info">👥 {{ capacityText(event) }}</p>
            </div>
        </article>
    </router-link>
</template>

<script setup>
    import { STATUS_TONE, capacityText, formatDateTime } from '../format'

    defineProps({ event: { type: Object, required: true } })
</script>

<style scoped>
    .event-card-link {
        text-decoration: none;
        color: inherit;
        display: block;
        height: 100%;
    }
    .event-card {
        height: 100%;
        border: 1px solid var(--border);
        border-radius: 10px;
        overflow: hidden;
        background: white;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .event-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.08);
    }
    .card-cover {
        height: 120px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: linear-gradient(135deg, #004d99, #2d7fc1);
        color: rgba(255, 255, 255, 0.92);
        font-size: 1.4rem;
        font-weight: 700;
        letter-spacing: 0.1em;
    }
    .card-content {
        padding: 14px 16px 16px;
    }
    .card-top {
        display: flex;
        gap: 6px;
        flex-wrap: wrap;
    }
    .card-title {
        margin: 8px 0;
        font-size: 1.1rem;
        overflow-wrap: anywhere;
    }
    .card-info {
        margin: 2px 0;
        color: var(--muted);
        font-size: 0.92rem;
        overflow-wrap: anywhere;
    }
</style>
