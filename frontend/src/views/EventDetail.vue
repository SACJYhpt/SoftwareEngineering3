<template>
    <div class="event-detail">
        <button @click="router.back()" class="back-btn">← 返回列表</button>
        
        <div v-if="event">
            <h1 style="color: black;">{{ event.title }}</h1>
            <p>正在查看活動 ID: {{ route.params.id }} 詳細資訊</p>
            <div class="placeholder-box">我是 Google Map 和報名按鈕</div>
        </div>
    </div>
</template>

<script setup>
    import { useRoute, useRouter } from 'vue-router'

    const route = useRoute() 
    const router = useRouter() 

    const event = { title: "活動詳細資訊" } // 資料
</script>

<style scoped>
    .event-detail {
        max-width: 800px;
        margin: 40px auto;
        padding: 24px;
        background: white;
        border-radius: 8px;
    }
    .back-btn {
        background: transparent;
        border: none;
        color: #004d99;
        cursor: pointer;
        font-size: 1rem;
        margin-bottom: 20px;
    }
    .placeholder-box {
        margin-top: 20px;
        padding: 40px;
        background-color: #f0f0f0;
        text-align: center;
        color: #888;
        border-radius: 8px;
    }
</style>