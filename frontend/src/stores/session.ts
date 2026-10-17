import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, ApiError } from '@/api/client'
import type { Me, MePatch } from '@/api/types'

export const useSessionStore = defineStore('session', () => {
  const me = ref<Me | null>(null)
  const loaded = ref(false)

  async function load() {
    try {
      me.value = await api<Me>('/me')
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error
      me.value = null
    } finally {
      loaded.value = true
    }
  }

  async function update(patch: MePatch) {
    me.value = await api<Me>('/me', { method: 'PATCH', json: patch })
  }

  // Development-only sign-in until M1 adds real accounts.
  async function devLogin(email = 'test@example.com') {
    me.value = await api<Me>('/dev/login', { json: { email } })
  }

  async function logout() {
    await api<void>('/dev/logout', { method: 'POST' })
    me.value = null
  }

  return { me, loaded, load, update, devLogin, logout }
})
