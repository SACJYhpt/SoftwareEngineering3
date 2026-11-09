<template>
    <div class="app-container">
        <Navbar />
        <!-- 根據網址切換頁面 -->
        <router-view />
    </div>
</template>

<script setup>
    import Navbar from './components/Navbar.vue'
</script>
