import { useSyncExternalStore } from 'react'
import { pageFromPath } from './navigation'

function subscribe(callback) {
  window.addEventListener('popstate', callback)
  window.addEventListener('kbo:navigation', callback)
  return () => {
    window.removeEventListener('popstate', callback)
    window.removeEventListener('kbo:navigation', callback)
  }
}

export function useRoute() {
  const href = useSyncExternalStore(subscribe, () => window.location.href)
  const url = new URL(href)
  return { page: pageFromPath(url.pathname), query: url.searchParams }
}
