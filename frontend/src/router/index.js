import { createRouter, createWebHistory } from 'vue-router'
import { isAdmin, isLoggedIn, managedUnits, refreshUser } from '../auth'
import Home from '../views/Home.vue'
import EventDetail from '../views/EventDetail.vue'
import Login from '../views/Login.vue'
import Register from '../views/Register.vue'
import VerifyEmail from '../views/VerifyEmail.vue'
import ForgotPassword from '../views/ForgotPassword.vue'
import ResetPassword from '../views/ResetPassword.vue'
import Faq from '../views/Faq.vue'
import MyEvents from '../views/MyEvents.vue'
import CreateEvent from '../views/CreateEvent.vue'
import ManageEvents from '../views/ManageEvents.vue'
import EditEvent from '../views/EditEvent.vue'
import Roster from '../views/Roster.vue'
import OrganizerTerms from '../views/OrganizerTerms.vue'
import Admin from '../views/Admin.vue'

const routes = [
    { path: '/', component: Home }, // 首頁、搜尋、篩選 (ER-US-B01、B04、B05)
    { path: '/events/:id(\\d+)', component: EventDetail }, // 活動詳情、分享、取消報名 (ER-US-B02、B11、E02)
    { path: '/event/:id(\\d+)', redirect: (to) => `/events/${to.params.id}` }, // 舊網址相容
    { path: '/login', component: Login }, // 登入 (ER-US-A04、A07、D02)
    { path: '/register', component: Register }, // 註冊與個資同意 (ER-US-A01、A02)
    { path: '/verify-email', component: VerifyEmail }, // 信箱驗證、重寄 (ER-US-A01、A03)
    { path: '/forgot-password', component: ForgotPassword }, // 忘記密碼 (ER-US-A08)
    { path: '/reset-password', component: ResetPassword }, // 重設密碼 (ER-US-A08)
    { path: '/faq', component: Faq }, // 常見問題 (ER-US-B17)
    { path: '/me/events', component: MyEvents, meta: { requiresAuth: true } }, // 我的活動、歷史 (ER-US-E01、H03)
    { path: '/organizer-terms', component: OrganizerTerms, meta: { requiresManager: true } }, // 主辦規範 (ER-US-I16)
    { path: '/events/new', component: CreateEvent, meta: { requiresManager: true } }, // 建立活動 (ER-US-C01)
    { path: '/manage', component: ManageEvents, meta: { requiresManager: true } }, // 單位活動 (ER-US-C15、F07、B11)
    { path: '/manage/events/:id(\\d+)/edit', component: EditEvent, meta: { requiresManager: true } }, // 修改活動 (ER-US-F01)
    { path: '/manage/events/:id(\\d+)/registrations', component: Roster, meta: { requiresManager: true } }, // 名單 (ER-US-G01)
    { path: '/admin', component: Admin, meta: { requiresAdmin: true } }, // 系統管理 (ER-US-I01、I02、I05、I06、I12、J02、J03)
    { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
    history: createWebHistory(),
    routes,
})

// The backend re-checks every permission; these guards only keep the UI consistent.
router.beforeEach(async (to) => {
    const { requiresAuth, requiresManager, requiresAdmin } = to.meta
    if (!requiresAuth && !requiresManager && !requiresAdmin) return true
    if (!isLoggedIn.value) return { path: '/login', query: { redirect: to.fullPath } }
    try {
        // Unit grants can change at any time (ER-US-I02); refresh before guarded pages.
        await refreshUser()
    } catch {
        return { path: '/login', query: { redirect: to.fullPath } }
    }
    if (requiresManager && managedUnits.value.length === 0) return '/'
    if (requiresAdmin && !isAdmin.value) return '/'
    return true
})

export default router
