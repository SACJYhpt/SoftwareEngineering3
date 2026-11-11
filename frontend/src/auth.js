// Login state. sessionStorage (not localStorage) so closing the browser on a
// shared computer drops the token; logout also revokes it on the server.
import { computed, reactive } from 'vue'
import { request } from './api.js'

const KEY = 'ntou-events-session'

function load() {
  try {
    return JSON.parse(sessionStorage.getItem(KEY)) || { token: null, user: null }
  } catch {
    return { token: null, user: null }
  }
}

export const auth = reactive(load())

function save() {
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ token: auth.token, user: auth.user }))
  } catch {
    // Storage may be blocked (private mode); the session then lasts for this page only.
  }
}

export function clearSession() {
  auth.token = null
  auth.user = null
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    // ignore
  }
}

export const isLoggedIn = computed(() => Boolean(auth.token))
export const managedUnits = computed(() => (auth.user && auth.user.managed_units) || [])

export async function login(email, password) {
  const result = await request('/auth/login', { method: 'POST', body: { email, password }, withAuth: false })
  auth.token = result.access_token
  auth.user = result.user
  save()
  return result.user
}

export async function logout() {
  try {
    if (auth.token) await request('/auth/logout', { method: 'POST' })
  } finally {
    clearSession()
  }
}

// Unit grants can change after login (ER-US-I02), so refresh them before manager pages.
export async function refreshUser() {
  if (!auth.token) return null
  auth.user = await request('/auth/me')
  save()
  return auth.user
}
