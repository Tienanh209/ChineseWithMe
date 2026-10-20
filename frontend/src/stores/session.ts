import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, ApiError } from '@/api/client'
import type { AuthConfig, Me, MePatch, RegisterBody } from '@/api/types'

export const useSessionStore = defineStore('session', () => {
  const me = ref<Me | null>(null)
  const loaded = ref(false)
  const googleClientId = ref<string | null>(null)

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

  // One shared request, so the router guard and App.vue do not both fetch /me.
  let pending: Promise<void> | null = null
  function ensureLoaded(): Promise<void> {
    if (loaded.value) return Promise.resolve()
    pending ??= load().finally(() => (pending = null))
    return pending
  }

  async function loadConfig() {
    if (googleClientId.value !== null) return
    try {
      googleClientId.value = (await api<AuthConfig>('/auth/config')).google_client_id ?? ''
    } catch {
      googleClientId.value = '' // no Google button; email sign-in still works
    }
  }

  async function register(body: RegisterBody) {
    me.value = await api<Me>('/auth/register', { json: body })
  }

  async function login(email: string, password: string) {
    me.value = await api<Me>('/auth/login', { json: { email, password } })
  }

  async function loginWithGoogle(credential: string) {
    me.value = await api<Me>('/auth/google', { json: { credential } })
  }

  async function logout() {
    await api<void>('/auth/logout', { method: 'POST' })
    me.value = null
  }

  async function update(patch: MePatch) {
    me.value = await api<Me>('/me', { method: 'PATCH', json: patch })
  }

  async function changePassword(currentPassword: string | null, newPassword: string) {
    me.value = await api<Me>('/me/password', {
      method: 'PUT',
      json: { current_password: currentPassword, new_password: newPassword },
    })
  }

  async function linkGoogle(credential: string, password: string | null) {
    me.value = await api<Me>('/auth/google/link', { json: { credential, password } })
  }

  async function unlinkGoogle() {
    await api<void>('/auth/google', { method: 'DELETE' })
    await load()
  }

  async function deleteAccount(proof: { password?: string; credential?: string }) {
    await api<void>('/me', { method: 'DELETE', json: proof })
    me.value = null
  }

  async function verifyEmail(token: string) {
    await api<void>('/auth/verify-email', { json: { token } })
    if (me.value) await load()
  }

  const resendVerification = () => api<void>('/auth/resend-verification', { method: 'POST' })
  const forgotPassword = (email: string) => api<void>('/auth/forgot-password', { json: { email } })
  const resetPassword = (token: string, password: string) =>
    api<void>('/auth/reset-password', { json: { token, password } })

  return {
    me,
    loaded,
    googleClientId,
    load,
    ensureLoaded,
    loadConfig,
    register,
    login,
    loginWithGoogle,
    logout,
    update,
    changePassword,
    linkGoogle,
    unlinkGoogle,
    deleteAccount,
    verifyEmail,
    resendVerification,
    forgotPassword,
    resetPassword,
  }
})
