<template>
    <nav class="navbar">
        <router-link to="/" class="nav-brand">海大活動報名系統</router-link>
        <div class="nav-links">
            <router-link to="/faq" class="nav-link">常見問題</router-link>
            <router-link v-if="isLoggedIn" to="/me/events" class="nav-link">我的活動</router-link>
            <router-link v-if="managedUnits.length" to="/manage" class="nav-link">活動管理</router-link>
            <router-link v-if="isAdmin" to="/admin" class="nav-link">系統管理</router-link>
        </div>
        <div class="nav-actions">
            <template v-if="isLoggedIn">
                <span class="nav-user" :title="auth.user && auth.user.email">{{ auth.user && auth.user.name }}</span>
                <button class="btn btn-outline" :disabled="busy" @click="onLogout">登出</button>
            </template>
            <template v-else>
                <router-link to="/register" class="btn btn-outline">註冊</router-link>
                <router-link :to="{ path: '/login', query: { redirect: loginRedirect } }" class="btn">登入</router-link>
            </template>
        </div>
    </nav>
</template>

<script setup>
    import { computed, ref } from 'vue'
    import { useRoute, useRouter } from 'vue-router'
    import { auth, isAdmin, isLoggedIn, logout, managedUnits } from '../auth'

    const route = useRoute()
    const router = useRouter()
    const busy = ref(false)

    // Return to the current page after logging in, except from the account pages themselves.
    const ACCOUNT_PAGES = ['/login', '/register', '/verify-email', '/forgot-password', '/reset-password']
    const loginRedirect = computed(() => (ACCOUNT_PAGES.includes(route.path) ? route.query.redirect : route.fullPath))

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
    .nav-links {
        display: flex;
        flex-wrap: wrap;
        gap: 4px 14px;
        flex: 1;
    }
    .nav-link {
        color: var(--text);
        text-decoration: none;
        font-weight: 600;
        padding: 6px 2px;
    }
    .nav-link.router-link-active {
        color: var(--brand);
        border-bottom: 2px solid var(--brand);
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
    /* Small screens: brand and buttons on the first row, page links on their own row below. */
    @media (max-width: 640px) {
        .nav-brand {
            flex: 1;
        }
        .nav-links {
            order: 3;
            flex-basis: 100%;
            gap: 4px 18px;
        }
    }
    @media (max-width: 480px) {
        .nav-user {
            display: none;
        }
    }
</style>
