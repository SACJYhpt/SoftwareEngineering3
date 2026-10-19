import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import EventDetail from '../views/EventDetail.vue'

const routes = [
    { path: '/', component: Home }, // 首頁
    { path: '/event/:id', component: EventDetail } // 活動詳情頁 (網址帶有 id)
]

const router = createRouter({
    history: createWebHistory(),
    routes
})

export default router