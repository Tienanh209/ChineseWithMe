/** Google Identity Services: loads the script once and wraps the pieces we use. */

interface CredentialResponse {
  credential: string
}

interface GoogleId {
  initialize(config: {
    client_id: string
    callback: (response: CredentialResponse) => void
    auto_select?: boolean
    cancel_on_tap_outside?: boolean
  }): void
  renderButton(parent: HTMLElement, options: Record<string, unknown>): void
  prompt(): void
  cancel(): void
}

declare global {
  interface Window {
    google?: { accounts: { id: GoogleId } }
  }
}

const SCRIPT_SRC = 'https://accounts.google.com/gsi/client'
let loading: Promise<GoogleId> | null = null

export function loadGoogleIdentity(): Promise<GoogleId> {
  if (window.google?.accounts.id) return Promise.resolve(window.google.accounts.id)
  loading ??= new Promise<GoogleId>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = SCRIPT_SRC
    script.async = true
    script.onload = () => {
      const id = window.google?.accounts.id
      if (id) resolve(id)
      else reject(new Error('Google Identity Services did not initialise'))
    }
    script.onerror = () => reject(new Error('Could not load Google Identity Services'))
    document.head.appendChild(script)
  }).catch((error) => {
    loading = null // allow a retry, e.g. after a blocked request
    throw error
  })
  return loading
}
