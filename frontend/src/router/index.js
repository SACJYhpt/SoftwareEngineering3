import { createRouter, createWebHistory } from 'vue-router'
import { isLoggedIn, managedUnits, refreshUser } from '../auth'
import Home from '../views/Home.vue'
import EventDetail from '../views/EventDetail.vue'
import Login from '../views/Login.vue'
import CreateEvent from '../views/CreateEvent.vue'

const routes = [
    { path: '/', component: Home }, // 首頁 (ER-US-B01)
    { path: '/login', component: Login }, // 登入 (ER-US-A04、D02)
    { path: '/events/new', component: CreateEvent, meta: { requiresManager: true } }, // 建立活動 (ER-US-C01)
    { path: '/events/:id(\\d+)', component: EventDetail }, // 活動詳情 (ER-US-B02)
    { path: '/event/:id(\\d+)', redirect: (to) => `/events/${to.params.id}` }, // 舊網址相容
    { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
    history: createWebHistory(),
    routes,
})

// The backend re-checks every permission; these guards only keep the UI consistent.
router.beforeEach(async (to) => {
    if (!to.meta.requiresManager) return true
    if (!isLoggedIn.value) return { path: '/login', query: { redirect: to.fullPath } }
    try {
        await refreshUser()
    } catch {
        return { path: '/login', query: { redirect: to.fullPath } }
    }
    return managedUnits.value.length > 0 ? true : '/'
})

export default router
