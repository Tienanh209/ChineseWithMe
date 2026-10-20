import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { Me } from '@/api/types'
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
