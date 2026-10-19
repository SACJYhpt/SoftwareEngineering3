<template>
    <div class="app-container">
        <Navbar />
            <!-- 根據網址不同，自動切換成 Home 或 EventDetail -->
        <router-view /> 
    </div>
</template>

<script setup>
    import Navbar from './components/Navbar.vue'
</script>

<style>
    body {
        margin: 0;
        font-family: sans-serif;
        background-color: #f5f7fa;
    }
</style>