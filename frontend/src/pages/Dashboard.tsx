import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'

function apiBaseUrl(): string {
  const base = (import.meta.env.VITE_API_URL as string | undefined) || ''
  return base.replace(/\/+$/, '')
}

type AuthState =
  | { status: 'loading' }
  | { status: 'authenticated'; shop: string }
  | { status: 'unauthenticated' }

export default function Dashboard() {
  const [auth, setAuth] = useState<AuthState>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false

    async function loadAuth() {
      const base = apiBaseUrl()
      if (!base) {
        if (!cancelled) {
          setAuth({ status: 'unauthenticated' })
        }
        return
      }

      try {
        const response = await fetch(`${base}/api/auth/me`, { credentials: 'include' })
        if (!response.ok) {
          if (!cancelled) {
            setAuth({ status: 'unauthenticated' })
          }
          return
        }
        const data = (await response.json()) as { shop?: string; authenticated?: boolean }
        if (!cancelled && data.authenticated && data.shop) {
          setAuth({ status: 'authenticated', shop: data.shop })
          return
        }
        if (!cancelled) {
          setAuth({ status: 'unauthenticated' })
        }
      } catch {
        if (!cancelled) {
          setAuth({ status: 'unauthenticated' })
        }
      }
    }

    void loadAuth()
    return () => {
      cancelled = true
    }
  }, [])

  if (auth.status === 'loading') {
    return (
      <div
        style={{
          minHeight: '100vh',
          background: '#08080F',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexDirection: 'column',
          gap: '20px',
        }}
      >
        <img src="/perspicor-mark.png" alt="Perspicor" width={48} height={48} decoding="async" />
        <div
          style={{
            width: '32px',
            height: '32px',
            border: '3px solid #1E1E35',
            borderTopColor: '#5C6BFF',
            borderRadius: '50%',
            animation: 'dashboard-spin 0.8s linear infinite',
          }}
        />
        <style>{`@keyframes dashboard-spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    )
  }

  if (auth.status === 'unauthenticated') {
    return <Navigate to="/connect" replace />
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        background: '#08080F',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        padding: '48px 24px',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          marginBottom: '48px',
        }}
      >
        <img src="/perspicor-mark.png" alt="" width={40} height={40} decoding="async" />
        <span
          style={{
            color: '#FFFFFF',
            fontSize: '18px',
            fontWeight: 800,
            letterSpacing: '0.22em',
          }}
        >
          PERSPICOR
        </span>
      </div>

      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '12px',
          textAlign: 'center',
          maxWidth: '420px',
        }}
      >
        <p style={{ color: '#8888AA', fontSize: '14px', margin: 0 }}>Welcome back</p>
        <p style={{ color: '#5C6BFF', fontSize: '18px', fontWeight: 700, margin: 0 }}>{auth.shop}</p>
        <p style={{ color: '#8888AA', fontSize: '14px', margin: '8px 0 0', lineHeight: 1.6 }}>
          Your daily report is running. Full dashboard coming soon.
        </p>
      </div>
    </div>
  )
}
