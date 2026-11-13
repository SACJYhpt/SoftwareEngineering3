<template>
    <main class="page">
        <header class="hero-banner">
            <h1>探索校園活動，豐富大學生活</h1>
            <p>搜尋活動或主辦單位，再依活動類型與日期縮小範圍</p>
        </header>

        <!-- 關鍵字、類型、日期可組合使用 (ER-US-B04、B05) -->
        <form class="panel filters" aria-label="活動搜尋與篩選" @submit.prevent="search">
            <div class="search-row">
                <input v-model.trim="filters.q" type="search" maxlength="200" placeholder="活動名稱、描述、地點、類型或主辦單位，可用簡稱 (如「資工」)" aria-label="關鍵字" />
                <button class="btn" type="submit">搜尋</button>
            </div>
            <div class="filter-row">
                <label>
                    活動類型
                    <select v-model="filters.type">
                        <option value="">全部類型</option>
                        <option v-for="item in types" :key="item.id" :value="item.name">{{ item.name }}</option>
                    </select>
                </label>
                <label>
                    開始日期
                    <input v-model="filters.date_from" type="date" />
                </label>
                <label>
                    結束日期
                    <input v-model="filters.date_to" type="date" />
                </label>
                <button class="btn btn-outline" type="button" :disabled="!hasFilters" @click="clearFilters">清除條件</button>
            </div>
        </form>

        <p v-if="loading" class="muted">載入中…</p>
        <div v-else-if="error" class="alert alert-error">
            {{ error }} <button class="btn btn-outline" @click="search">重新載入</button>
        </div>
        <p v-else-if="events.length === 0" class="muted empty">
            {{ hasFilters ? '找不到符合的活動' : '目前沒有即將舉行的活動。' }}
        </p>
        <template v-else>
            <div class="event-grid">
                <EventCard v-for="event in events" :key="event.id" :event="event" />
            </div>
            <div class="more">
                <p class="muted">已顯示 {{ events.length }} / {{ total }} 個活動</p>
                <button v-if="events.length < total" class="btn btn-outline" :disabled="loadingMore" @click="loadMore">
                    {{ loadingMore ? '載入中…' : '載入更多' }}
                </button>
                <p v-if="moreError" class="alert alert-error">{{ moreError }}</p>
            </div>
        </template>
    </main>
</template>

<script setup>
    import { computed, onMounted, reactive, ref, watch } from 'vue'
    import { useRoute, useRouter } from 'vue-router'
    import { request } from '../api'
    import EventCard from '../components/EventCard.vue'

    const PAGE_SIZE = 30
    const EMPTY = { q: '', type: '', date_from: '', date_to: '' }
    const route = useRoute()
    const router = useRouter()

    // The search conditions live in the URL (?q=&type=&date_from=&date_to=), so a refreshed
    // or shared link shows the same results (ER-US-B05).
    function filtersFromQuery(query) {
        const result = { ...EMPTY }
        for (const key of Object.keys(EMPTY)) {
            const value = query[key]
            if (typeof value === 'string') result[key] = key === 'q' ? value.trim().slice(0, 200) : value
        }
        return result
    }

    const filters = reactive(filtersFromQuery(route.query))
    const types = ref([])
    const events = ref([])
    const total = ref(0)
    const loading = ref(true)
    const loadingMore = ref(false)
    const error = ref('')
    const moreError = ref('')
    let searchId = 0

    const hasFilters = computed(() => Object.values(filters).some(Boolean))

    function query(offset) {
        const params = new URLSearchParams({ limit: PAGE_SIZE, offset })
        for (const [key, value] of Object.entries(filters)) {
            if (value) params.set(key, value)
        }
        return `/events?${params}`
    }

    async function search() {
        if (filters.date_from && filters.date_to && filters.date_from > filters.date_to) {
            error.value = '開始日期不可晚於結束日期'
            events.value = []
            loading.value = false
            return
        }
        syncUrl()
        const current = ++searchId
        loading.value = true
        error.value = ''
        moreError.value = ''
        try {
            const page = await request(query(0), { withTotal: true, guestRetry: true })
            if (current !== searchId) return // a newer search has started
            events.value = page.data
            total.value = page.total
        } catch (e) {
            if (current === searchId) error.value = e.message
        } finally {
            if (current === searchId) loading.value = false
        }
    }

    async function loadMore() {
        loadingMore.value = true
        moreError.value = ''
        try {
            const page = await request(query(events.value.length), { withTotal: true, guestRetry: true })
            // Skip events already shown, in case the list shifted between requests.
            const seen = new Set(events.value.map((event) => event.id))
            events.value = events.value.concat(page.data.filter((event) => !seen.has(event.id)))
            total.value = page.total
        } catch (e) {
            moreError.value = e.message
        } finally {
            loadingMore.value = false
        }
    }

    function clearFilters() {
        Object.assign(filters, EMPTY)
    }

    function sameAsUrl(values) {
        return Object.keys(EMPTY).every((key) => (route.query[key] || '') === values[key])
    }

    function syncUrl() {
        if (sameAsUrl(filters)) return
        const query = {}
        for (const [key, value] of Object.entries(filters)) {
            if (value) query[key] = value
        }
        router.replace({ query })
    }

    // Back / forward between searches restores that search's conditions.
    watch(() => route.query, (query) => {
        if (route.path !== '/') return
        const next = filtersFromQuery(query)
        if (Object.keys(EMPTY).some((key) => next[key] !== filters[key])) {
            const keywordChanged = next.q !== filters.q
            Object.assign(filters, next)
            // Type, date and cleared-keyword changes trigger their own watchers; a new keyword does not.
            if (keywordChanged && next.q) search()
        }
    })

    // Type and dates apply as soon as they change; the keyword applies on 搜尋 / Enter.
    watch(() => [filters.type, filters.date_from, filters.date_to], search)
    watch(() => filters.q, (value) => {
        if (!value) search()
    })

    onMounted(async () => {
        try {
            types.value = await request('/event-types', { withAuth: false })
        } catch {
            // The list still works without the type filter.
        }
        await search()
    })
</script>

<style scoped>
    .hero-banner {
        background-color: var(--brand);
        color: white;
        padding: 32px 20px;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 20px;
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
    .filters {
        margin-bottom: 24px;
        padding: 16px;
    }
    .search-row {
        display: flex;
        gap: 8px;
    }
    .search-row input,
    .filter-row input,
    .filter-row select {
        width: 100%;
        min-width: 0;
        padding: 9px 10px;
        border: 1px solid var(--border);
        border-radius: 6px;
        background: #fff;
    }
    .filter-row {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(min(100%, 160px), 1fr));
        align-items: end;
        gap: 12px;
        margin-top: 12px;
    }
    .filter-row label {
        display: grid;
        gap: 4px;
        font-size: 0.9rem;
        font-weight: 600;
    }
    .event-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr));
        gap: 20px;
    }
    .more {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 8px;
        margin-top: 24px;
    }
    .more p {
        margin: 0;
    }
    .empty {
        text-align: center;
        padding: 40px 0;
    }
</style>
