import assert from 'node:assert/strict'
import { pageFromPath, pageUrl, navigate, updateQuery, followLink } from './navigation.js'

assert.equal(pageFromPath('/players/'), 'players')
assert.equal(pageFromPath('/unknown'), 'home')
assert.equal(pageUrl('home'), '/')
const url = new URL(pageUrl('players', { team: '삼성', sort: 'WAR', q: '김 현수' }), 'http://localhost')
assert.equal(url.searchParams.get('team'), '삼성')
assert.equal(url.searchParams.get('q'), '김 현수')
const events = []
const history = []
globalThis.window = {
  location: new URL('http://localhost/players?team=LG'),
  history: {
    pushState: (_, __, path) => { history.push(path); window.location = new URL(path, 'http://localhost') },
    replaceState: (_, __, path) => { history[history.length - 1] = path; window.location = new URL(path, 'http://localhost') },
  },
  dispatchEvent: (event) => events.push(event.type),
}
updateQuery({ sort: 'WAR', dir: 'asc' })
assert.equal(window.location.searchParams.get('team'), 'LG')
assert.equal(window.location.searchParams.get('sort'), 'WAR')
updateQuery({ q: '김' }, true)
assert.equal(history.length, 1)
updateQuery({ team: null })
assert.equal(window.location.searchParams.has('team'), false)
navigate('/teams?team=삼성')
assert.equal(window.location.pathname, '/teams')
assert.equal(events.length, 4)
let prevented = false
followLink({ button: 0, ctrlKey: true, preventDefault: () => { prevented = true } })
assert.equal(prevented, false)
