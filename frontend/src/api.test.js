import test, { afterEach } from 'node:test'
import assert from 'node:assert/strict'
import { auth, clearSession } from './auth.js'
import { request } from './api.js'

const originalFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = originalFetch; clearSession() })

test('public account calls send JSON without an existing login token', async () => {
  auth.token = 'existing-session'
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/auth/forgot-password')
    assert.equal(options.method, 'POST')
    assert.equal(options.headers.Authorization, undefined)
    assert.deepEqual(JSON.parse(options.body), { email: 'student@ntou.edu.tw' })
    return Response.json({ message: 'queued' }, { status: 202 })
  }
  assert.equal((await request('/auth/forgot-password', { method: 'POST', body: { email: 'student@ntou.edu.tw' }, withAuth: false })).message, 'queued')
})

test('authorized QR downloads return a PNG blob rather than parsing JSON', async () => {
  auth.token = 'manager-session'
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/events/1/qr')
    assert.equal(options.headers.Authorization, 'Bearer manager-session')
    return new Response(new Uint8Array([137, 80, 78, 71]), { headers: { 'Content-Type': 'image/png' } })
  }
  const blob = await request('/events/1/qr', { responseType: 'blob' })
  assert.equal(blob.type, 'image/png')
  assert.equal(blob.size, 4)
})

test('new SRD time validator messages identify the correct form field', async () => {
  globalThis.fetch = async () => Response.json({ detail: [{ loc: ['body'], msg: 'Value error, end_time must not be earlier than start_time' }] }, { status: 422 })
  await assert.rejects(request('/events', { method: 'POST', body: {} }), error =>
    error.code === 'VALIDATION_ERROR' && error.fieldErrors.end_time === '結束時間不可早於開始時間')
})

test('an expired session retries only publicly readable GET routes as a guest', async () => {
  auth.token = 'expired-session'
  let calls = 0
  globalThis.fetch = async (url, options) => {
    calls++
    if (calls === 1) return Response.json({ detail: { code: 'INVALID_TOKEN', message: 'expired' } }, { status: 401 })
    assert.equal(options.headers.Authorization, undefined)
    return Response.json([])
  }
  assert.deepEqual(await request('/events?q=Python'), [])
  assert.equal(calls, 2)
  assert.equal(auth.token, null)
})

test('an expired private request is not retried without authorization', async () => {
  auth.token = 'expired-session'
  let calls = 0
  globalThis.fetch = async () => {
    calls++
    return Response.json({ detail: { code: 'INVALID_TOKEN', message: 'expired' } }, { status: 401 })
  }
  await assert.rejects(request('/me/events'), error => error.code === 'INVALID_TOKEN')
  assert.equal(calls, 1)
})
