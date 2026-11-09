<template>
    <nav class="navbar">
        <router-link to="/" class="nav-brand">海大活動報名系統</router-link>
        <div class="nav-actions">
            <router-link v-if="managedUnits.length" to="/events/new" class="btn btn-outline">建立活動</router-link>
            <template v-if="isLoggedIn">
                <span class="nav-user" :title="auth.user && auth.user.email">{{ auth.user && auth.user.name }}</span>
                <button class="btn btn-outline" :disabled="busy" @click="onLogout">登出</button>
            </template>
            <router-link v-else :to="{ path: '/login', query: { redirect: loginRedirect } }" class="btn">登入</router-link>
        </div>
    </nav>
</template>

<script setup>
    import { computed, ref } from 'vue'
    import { useRoute, useRouter } from 'vue-router'
    import { auth, isLoggedIn, logout, managedUnits } from '../auth'

    const route = useRoute()
    const router = useRouter()
    const busy = ref(false)

    // Return to the current page after logging in, except from the login page itself.
    const loginRedirect = computed(() => (route.path === '/login' ? route.query.redirect : route.fullPath))

    async function onLogout() {
        busy.value = true
        try {
            await logout()
        } finally {
            busy.value = false
            router.push('/')
        }
    }
</script>

<style scoped>
    .navbar {
        display: flex;
        flex-wrap: wrap;
        justify-content: space-between;
        align-items: center;
        gap: 8px 16px;
        padding: 10px 16px;
        background-color: #fff;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.08);
        position: sticky;
        top: 0;
        z-index: 100;
    }
    .nav-brand {
        font-size: 1.2rem;
        font-weight: bold;
        color: var(--brand);
        text-decoration: none;
    }
    .nav-actions {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 8px;
    }
    .nav-user {
        max-width: 12em;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        color: var(--muted);
    }
    @media (max-width: 480px) {
        .nav-user {
            display: none;
        }
    }
</style>
