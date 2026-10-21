import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { Me } from '@/api/types'
import { forgetLookup, lastLookup } from '@/lib/lastLookup'
import { useSessionStore } from '@/stores/session'
import router from '..'

const me = { id: 1, email: 'a@example.com', has_password: true } as Me

beforeEach(async () => {
  setActivePinia(createPinia())
  await router.push('/')
})

function signedOut() {
  const session = useSessionStore()
  session.loaded = true
  session.me = null
}
function signedIn() {
  const session = useSessionStore()
  session.loaded = true
  session.me = me
}

describe('route guards', () => {
  it('sends signed-out visitors from /profile to sign-in and remembers where they were going', async () => {
    signedOut()
    await router.push('/profile')
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.next).toBe('/profile')
  })

  it('keeps flashcards for signed-in users, and brings you back after signing in', async () => {
    signedOut()
    await router.push('/flashcards')
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.next).toBe('/flashcards')
    signedIn()
    await router.push('/flashcards')
    expect(router.currentRoute.value.name).toBe('flashcards')
  })

  it('lets signed-in users into /profile', async () => {
    signedIn()
    await router.push('/profile')
    expect(router.currentRoute.value.name).toBe('profile')
  })

  it('sends signed-in users away from sign-in and register, honouring a safe next', async () => {
    signedIn()
    await router.push('/login')
    expect(router.currentRoute.value.path).toBe('/')
    await router.push('/register?next=/lessons')
    expect(router.currentRoute.value.path).toBe('/lessons')
    await router.push('/login?next=//evil.example.com')
    expect(router.currentRoute.value.path).toBe('/')
  })

  it('leaves public pages alone', async () => {
    signedOut()
    for (const path of ['/verify-email', '/forgot-password', '/reset-password', '/lookup']) {
      await router.push(path)
      expect(router.currentRoute.value.path).toBe(path)
    }
  })
})

describe('look-up memory', () => {
  it('remembers the look-up page with its query, for "Back to search"', async () => {
    forgetLookup()
    signedOut()
    expect(lastLookup()).toBe('/lookup')
    await router.push('/lookup?q=xue&page=2')
    await router.push('/vocab/7')
    expect(lastLookup()).toBe('/lookup?q=xue&page=2') // a word page does not overwrite it
    await router.push('/lookup?level=A1')
    expect(lastLookup()).toBe('/lookup?level=A1')
    forgetLookup()
  })
})
