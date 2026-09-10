export const PAGES = ['home', 'standings', 'race', 'teams', 'schedule', 'players', 'zones', 'ops', 'ask']

export function pageFromPath(pathname) {
  const page = pathname.replace(/^\/+|\/+$/g, '')
  return PAGES.includes(page) ? page : 'home'
}

export function pageUrl(page, params = {}) {
  const path = PAGES.includes(page) && page !== 'home' ? `/${page}` : '/'
  const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value != null && value !== ''))
  return `${path}${query.size ? `?${query}` : ''}`
}

export function navigate(url, replace = false) {
  if (`${window.location.pathname}${window.location.search}` === url) return
  window.history[replace ? 'replaceState' : 'pushState']({}, '', url)
  window.dispatchEvent(new Event('kbo:navigation'))
}

export function updateQuery(values, replace = false) {
  const query = new URLSearchParams(window.location.search)
  for (const [key, value] of Object.entries(values)) {
    if (value == null || value === '') query.delete(key)
    else query.set(key, String(value))
  }
  navigate(`${window.location.pathname}${query.size ? `?${query}` : ''}`, replace)
}

export function followLink(event) {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
  event.preventDefault()
  const url = new URL(event.currentTarget.href)
  navigate(`${url.pathname}${url.search}`)
}
