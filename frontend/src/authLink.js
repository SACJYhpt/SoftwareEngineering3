// New mail links keep secrets in the fragment. Query tokens from older shared
// links are accepted too, then removed from the address after being read.
export function actionToken(route) {
  const fragment = new URLSearchParams((route.hash || '').replace(/^#/, ''))
  const queryToken = typeof route.query?.token === 'string' ? route.query.token : ''
  return fragment.get('token') || queryToken
}

export function withoutActionToken(route) {
  const query = { ...route.query }
  delete query.token
  const fragment = new URLSearchParams((route.hash || '').replace(/^#/, ''))
  let hash = route.hash || ''
  if (fragment.has('token')) {
    fragment.delete('token')
    hash = fragment.size ? '#' + fragment.toString() : ''
  }
  return { path: route.path, query, hash }
}
