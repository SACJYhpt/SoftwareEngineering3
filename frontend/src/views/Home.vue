<template>
    <main class="page">
        <header class="hero-banner">
            <h1>探索校園活動，豐富大學生活</h1>
            <p>搜尋活動名稱或描述，依活動類型與日期縮小範圍</p>
        </header>

        <section class="filter-panel panel" aria-label="活動搜尋與篩選">
            <form @submit.prevent="load">
                <div class="search-row">
                    <input v-model.trim="filters.q" type="search" placeholder="輸入活動名稱或關鍵字…" aria-label="關鍵字搜尋" />
                    <button class="btn" type="submit">搜尋</button>
                    <button class="btn btn-outline" type="button" @click="clearFilters">清除</button>
                </div>
                <div class="filter-row">
                    <label>活動類型
                        <select v-model="filters.type"><option value="">全部類型</option><option v-for="item in types" :key="item.id" :value="item.name">{{ item.name }}</option></select>
                    </label>
                    <label>開始日期 <input v-model="filters.date_from" type="date" /></label>
                    <label>結束日期 <input v-model="filters.date_to" type="date" /></label>
                    <button class="btn btn-outline" type="submit">套用篩選</button>
                </div>
            </form>
        </section>

        <p v-if="loading" class="muted">載入中…</p>
        <div v-else-if="error" class="alert alert-error">{{ error }} <button class="btn btn-outline" @click="load">重新載入</button></div>
        <p v-else-if="events.length === 0" class="muted empty">找不到符合條件的活動，請調整搜尋或篩選條件。</p>
        <div v-else class="event-grid">
            <EventCard v-for="event in events" :key="event.id" :event="event" />
        </div>
        <p v-if="!loading && !error" class="muted result-count">共找到 {{ events.length }} 筆活動</p>
    </main>
</template>

<script setup>
    import { onMounted, reactive, ref } from 'vue'
    import { request } from '../api'
    import EventCard from '../components/EventCard.vue'

    const events = ref([])
    const types = ref([])
    const loading = ref(true)
    const error = ref('')
    const filters = reactive({ q: '', type: '', date_from: '', date_to: '' })

    async function load() {
        loading.value = true
        error.value = ''
        try {
            const params = new URLSearchParams()
            if (filters.q) params.set('q', filters.q)
            if (filters.type) params.set('type', filters.type)
            if (filters.date_from) params.set('date_from', filters.date_from)
            if (filters.date_to) params.set('date_to', filters.date_to)
            events.value = await request('/events' + (params.size ? '?' + params.toString() : ''))
        } catch (e) { error.value = e.message }
        finally { loading.value = false }
    }

    async function clearFilters() {
        Object.assign(filters, { q: '', type: '', date_from: '', date_to: '' })
        await load()
    }

    onMounted(async () => {
        try { types.value = await request('/event-types', { withAuth: false }) } catch { /* filters remain usable */ }
        await load()
    })
</script>

<style scoped>
    .hero-banner { background-color: var(--brand); color: white; padding: 36px 20px; border-radius: 10px; text-align: center; margin-bottom: 20px; }
    .hero-banner h1 { color: white; margin: 0 0 8px; font-size: clamp(1.4rem, 4vw, 2rem); }
    .hero-banner p { margin: 0; opacity: .9; }
    .filter-panel { margin-bottom: 22px; }
    .search-row { display: grid; grid-template-columns: minmax(0,1fr) auto auto; gap: 8px; }
    .search-row input, .filter-row input, .filter-row select { min-width: 0; width: 100%; padding: 9px 10px; border: 1px solid var(--border); border-radius: 6px; background: white; }
    .filter-row { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; margin-top: 14px; }
    .filter-row label { display: grid; gap: 4px; min-width: 150px; flex: 1; font-size: .9rem; font-weight: 600; }
    .event-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr)); gap: 20px; }
    .empty { text-align: center; padding: 40px 0; }
    .result-count { text-align: right; font-size: .9rem; margin-top: 16px; }
    @media(max-width:560px) { .search-row { grid-template-columns: 1fr 1fr; } .search-row input { grid-column: 1/-1; } }
</style>
