import test from 'node:test'
import assert from 'node:assert/strict'
import { actionToken, withoutActionToken } from './authLink.js'

test('new fragment mail links take precedence over legacy query tokens', () => {
  assert.equal(actionToken({ hash: '#token=current', query: { token: 'old' } }), 'current')
  assert.equal(actionToken({ hash: '', query: { token: 'legacy' } }), 'legacy')
})

test('missing or repeated query tokens are not sent as malformed strings', () => {
  assert.equal(actionToken({ hash: '', query: {} }), '')
  assert.equal(actionToken({ hash: '', query: { token: ['one', 'two'] } }), '')
})

test('removing link secrets preserves unrelated route values and the source object', () => {
  const route = { path: '/reset-password', query: { token: 'legacy', next: '/' }, hash: '#token=secret&source=email' }
  assert.deepEqual(withoutActionToken(route), { path: '/reset-password', query: { next: '/' }, hash: '#source=email' })
  assert.equal(route.query.token, 'legacy')
})

test('ordinary anchors survive while a token-only fragment is removed', () => {
  assert.equal(withoutActionToken({ path: '/verify-email', query: {}, hash: '#token=secret' }).hash, '')
  assert.equal(withoutActionToken({ path: '/verify-email', query: {}, hash: '#help' }).hash, '#help')
})
