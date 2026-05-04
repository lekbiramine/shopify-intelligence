import { useEffect, useRef, useState } from 'react'
import type { FormEvent, MouseEvent } from 'react'
import { Route, Routes } from 'react-router-dom'

const pricingFeatures = [
  'Daily decision report, delivered to your inbox',
  'Revenue leak detection',
  'Dead inventory alerts',
  'VIP customer churn signals',
  'Abandoned checkout diagnosis',
  'Margin optimization insights',
]

function LandingPage() {
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [email, setEmail] = useState('')
  const [shopInput, setShopInput] = useState('')
  const [emailError, setEmailError] = useState('')
  const [shopError, setShopError] = useState('')
  const inputRef = useRef<HTMLInputElement | null>(null)
  const apiBaseUrl = import.meta.env.VITE_API_URL as string

  useEffect(() => {
    if (!isModalOpen) {
      return
    }

    inputRef.current?.focus()

    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsModalOpen(false)
      }
    }

    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [isModalOpen])

  function normalizeShopDomain(raw: string): string {
    return raw.trim().replace(/^https?:\/\//i, '').replace(/\/+$/g, '')
  }

  function openModal(event: MouseEvent<HTMLAnchorElement>) {
    event.preventDefault()
    setIsModalOpen(true)
  }

  function closeModal() {
    setIsModalOpen(false)
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmedEmail = email.trim()
    const normalizedShop = normalizeShopDomain(shopInput)
    let hasError = false
    const isEmailValid = trimmedEmail.includes('@') && trimmedEmail.includes('.')

    if (!trimmedEmail || !isEmailValid) {
      setEmailError('Please enter a valid email address.')
      hasError = true
    } else {
      setEmailError('')
    }

    if (!normalizedShop) {
      setShopError('Please enter your Shopify store URL.')
      inputRef.current?.focus()
      hasError = true
    } else {
      setShopError('')
    }

    if (hasError) {
      return
    }

    const redirectUrl = `${apiBaseUrl}/install?shop=${encodeURIComponent(normalizedShop)}&email=${encodeURIComponent(trimmedEmail)}`
    window.location.href = redirectUrl
  }

  return (
    <div className="site-shell">
      <header className="header">
        <div className="logo" aria-label="Perspicor logo">
          <img src="/favicon.svg" alt="Perspicor" />
          <span>PERSPICOR</span>
        </div>
        <a className="pill-button" href="#" onClick={openModal}>
          Diagnose My Store Free
        </a>
      </header>

      <main className="content">
        <section className="hero">
          <h1>Unmatched Perspicacity for Your Shopify Store</h1>
          <p className="hero-subheadline">
            Most Shopify apps show you numbers. Perspicor tells you exactly what to do — and what
            it costs you every day you wait.
          </p>
          <a className="primary-button" href="#" onClick={openModal}>
            Find Out What's Killing Your Revenue — Free
          </a>
          <p className="hero-footnote">No credit card. No setup. Your first diagnosis in 24 hours.</p>
        </section>

        <section className="problem">
          <h2>You&apos;re working harder. The numbers don&apos;t show it.</h2>
          <p className="problem-subheading">
            Most Shopify stores are bleeding revenue from 3 places they never check.
          </p>
          <div className="problem-grid">
            <article className="problem-card">
              <p>
                <strong>Dead inventory</strong> — Products sitting unsold for 90+ days. Every day
                they sit, your cash flow shrinks and your competitors take your buyers.
              </p>
            </article>
            <article className="problem-card">
              <p>
                <strong>Fading VIP customers</strong> — Your best customers are going quiet. You
                won&apos;t notice until they&apos;re gone — and replacing them costs 5x more.
              </p>
            </article>
            <article className="problem-card">
              <p>
                <strong>Abandoned checkouts</strong> — People wanted to buy. Something stopped
                them. You never found out what.
              </p>
            </article>
          </div>
        </section>

        <section className="how-it-works">
          <h2>How It Works</h2>
          <div className="how-cards">
            <article className="how-card">
              <p className="how-number">01</p>
              <h3>Connect in 60 seconds</h3>
              <p>Link your Shopify store. No setup, no spreadsheets, no consultants.</p>
            </article>
            <article className="how-card">
              <p className="how-number">02</p>
              <h3>We diagnose overnight</h3>
              <p>
                Perspicor scans your inventory, customers, checkouts, and margins while you sleep.
              </p>
            </article>
            <article className="how-card">
              <p className="how-number">03</p>
              <h3>Wake up to decisions</h3>
              <p>
                Not a dashboard. Not charts. A ranked list of exactly what to fix and what it costs
                you to wait.
              </p>
            </article>
          </div>
        </section>

        <section id="pricing" className="pricing">
          <article className="pricing-card">
            <p className="pricing-label">Early Access Price</p>
            <div className="price-row">
              <span className="price-old">$99/month</span>
              <span className="price-new">$79/month</span>
            </div>
            <ul className="feature-list">
              {pricingFeatures.map((feature) => (
                <li key={feature}>{feature}</li>
              ))}
            </ul>
            <a className="primary-button" href="#" onClick={openModal}>
              Find Out What's Killing Your Revenue — Free
            </a>
            <p className="pricing-footnote">Cancel anytime. No contracts.</p>
          </article>
        </section>
      </main>

      <footer className="footer">
        <p>© 2026 Perspicor. All rights reserved.</p>
      </footer>

      {isModalOpen && (
        <div className="modal-overlay" onClick={closeModal} role="presentation">
          <article className="modal-card" onClick={(event) => event.stopPropagation()}>
            <button className="modal-close" type="button" onClick={closeModal} aria-label="Close modal">
              ×
            </button>
            <h2>Enter your Shopify store URL</h2>
            <p className="modal-subtext">We&apos;ll connect securely via Shopify. Takes 60 seconds.</p>
            <form onSubmit={handleSubmit}>
              <label
                style={{
                  color: '#8888AA',
                  fontSize: '12px',
                  marginBottom: '6px',
                  display: 'block',
                }}
              >
                Your email
              </label>
              <input
                type="email"
                placeholder="your@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                style={{
                  background: '#08080F',
                  border: '1px solid #1E1E35',
                  borderRadius: '6px',
                  color: '#FFFFFF',
                  padding: '12px 16px',
                  fontSize: '14px',
                  width: '100%',
                  marginBottom: '12px',
                  boxSizing: 'border-box',
                }}
              />
              {emailError && (
                <p style={{ color: '#FF6B6B', margin: '0 0 12px 0', fontSize: '12px' }}>{emailError}</p>
              )}
              <label
                style={{
                  color: '#8888AA',
                  fontSize: '12px',
                  marginBottom: '6px',
                  display: 'block',
                }}
              >
                Your Shopify store URL
              </label>
              <input
                ref={inputRef}
                type="text"
                value={shopInput}
                onChange={(event) => setShopInput(event.target.value)}
                placeholder="mystore.myshopify.com"
                aria-label="Shopify store URL"
              />
              {shopError && (
                <p style={{ color: '#FF6B6B', margin: '6px 0 0 0', fontSize: '12px' }}>{shopError}</p>
              )}
              <button type="submit" className="primary-button modal-submit">
                Connect My Store
              </button>
            </form>
            <p className="modal-footnote">
              You&apos;ll be redirected to Shopify to approve access. We never store your password.
            </p>
          </article>
        </div>
      )}
    </div>
  )
}

function CheckYourEmailPage() {
  return (
    <div className="success-page">
      <article className="success-card">
        <div className="success-icon" aria-hidden="true">
          ✓
        </div>
        <h1>You&apos;re in. Check your email.</h1>
        <p>
          Your first Perspicor report is being generated. It will land in your inbox within 24
          hours. Close this tab and go run your store.
        </p>
      </article>
    </div>
  )
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/check-your-email" element={<CheckYourEmailPage />} />
    </Routes>
  )
}

export default App
