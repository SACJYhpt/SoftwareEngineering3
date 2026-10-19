<template>
    <router-link :to="`/event/${event.id}`" class="event-card-link">
        <div class="event-card">
        <img :src="event.image" alt="活動封面" class="card-image" />
        <div class="card-content">
            <h3 class="card-title">{{ event.title }}</h3>
            <p class="card-info">📅 {{ event.time }}</p>
            <p class="card-info">📍 {{ event.location }}</p>
            <p class="card-info">⚠️ {{ event.restriction}}</p>
        </div>
        </div>
    </router-link>
</template>

<script setup>
    defineProps({ event: Object })
</script>

<style scoped>
    .event-card-link {
        text-decoration: none;
        color: inherit;
        display: block;
    }
    .event-card {
        border: 1px solid #eaeaea;
        border-radius: 8px;
        overflow: hidden;
        background: white;
        transition: transform 0.2s;
    }
    .event-card:hover {
        transform: translateY(-4px);
    }
    .card-image {
        width: 100%;
        height: 160px;
        object-fit: cover;
    }
    .card-content {
        padding: 16px;
    }
    .card-title {
        margin: 0 0 8px;
        font-size: 1.1rem;
    }
    .card-info {
        margin: 4px 0;
        color: #666;
        font-size: 0.9rem;
    }
</style>