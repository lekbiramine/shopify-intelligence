import { type FormEvent, useState } from 'react'
import { Link, Navigate, Route, Routes } from 'react-router-dom'

function apiBaseUrl(): string {
  const base =
    (import.meta.env.VITE_API_BASE_URL as string | undefined) ||
    (import.meta.env.VITE_API_URL as string | undefined) ||
    ''
  return base.replace(/\/+$/, '')
}

function normalizeShopDomain(raw: string): string {
  return raw.trim().replace(/^https?:\/\//i, '').replace(/\/+$/g, '')
}

function SiteHeader() {
  return (
    <header className="site-header">
      <Link to="/" className="site-logo">
        <img className="site-logo-mark" src="/perspicor-mark.png" alt="" height={40} decoding="async" />
        <span className="site-logo-text">PERSPICOR</span>
      </Link>
    </header>
  )
}

function LandingPage() {
  return (
    <div className="lp-shell">
      <SiteHeader />

      <main className="lp-main">
        <section className="lp-hero" aria-labelledby="lp-hero-heading">
          <h1 id="lp-hero-heading" className="lp-hero-title">
            Unmatched Perspicacity for Your Shopify Store
          </h1>
          <p className="lp-hero-sub">
            Perspicor scans your Shopify store overnight and delivers a ranked list of revenue leaks — with the exact
            dollar amount you&apos;re losing and what to do about it.
          </p>

          <div className="lp-device-wrap">
            <div className="lp-device" aria-hidden="true">
              <div className="lp-device-notch" />
              <div className="lp-device-screen">
                <div className="lp-report-preview" style={{ position: 'relative', backgroundColor: '#08080F' }}>
                  <div style={{ padding: '20px 12px 20px', lineHeight: 'normal', textAlign: 'left' }}>
                    <div style={{ marginBottom: '14px' }}>
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          color: '#8888AA',
                          fontSize: '13px',
                          textTransform: 'uppercase',
                          letterSpacing: '2px',
                        }}
                      >
                        <span>Northwind Commerce</span>
                        <span>May 4, 2026</span>
                      </div>
                      <div style={{ height: '1px', backgroundColor: '#5C6BFF', marginTop: '8px' }} />
                      <div style={{ marginTop: '10px' }}>
                        <span
                          style={{
                            display: 'inline-block',
                            padding: '5px 12px',
                            borderRadius: '999px',
                            backgroundColor: '#2B0D1A',
                            color: '#FF6B6B',
                            border: '1px solid #FF6B6B',
                            fontSize: '11px',
                            fontWeight: 700,
                            letterSpacing: '0.4px',
                          }}
                        >
                          CRITICAL
                        </span>
                      </div>
                    </div>

                    <div
                      style={{
                        marginBottom: '12px',
                        backgroundColor: '#12121E',
                        border: '1px solid #1E1E35',
                        borderRadius: '8px',
                      }}
                    >
                      <div
                        style={{
                          padding: '24px 24px 8px 24px',
                          color: '#8888AA',
                          fontSize: '11px',
                          textTransform: 'uppercase',
                          letterSpacing: '2px',
                        }}
                      >
                        Today&apos;s Opportunity
                      </div>
                      <div style={{ display: 'flex', padding: '0 24px 8px 24px' }}>
                        <div style={{ flex: 1, paddingRight: '10px' }}>
                          <div
                            style={{
                              color: '#8888AA',
                              fontSize: '11px',
                              textTransform: 'uppercase',
                              letterSpacing: '1px',
                              marginBottom: '4px',
                            }}
                          >
                            Daily Impact
                          </div>
                          <div style={{ color: '#5C6BFF', fontSize: '28px', lineHeight: 1.2, fontWeight: 800 }}>
                            $3,498.12
                          </div>
                        </div>
                        <div style={{ flex: 1, padding: '0 10px' }}>
                          <div
                            style={{
                              color: '#8888AA',
                              fontSize: '11px',
                              textTransform: 'uppercase',
                              letterSpacing: '1px',
                              marginBottom: '4px',
                            }}
                          >
                            Total Value
                          </div>
                          <div style={{ color: '#5C6BFF', fontSize: '28px', lineHeight: 1.2, fontWeight: 800 }}>
                            $48,973.65
                          </div>
                        </div>
                        <div style={{ flex: 1, paddingLeft: '10px' }}>
                          <div
                            style={{
                              color: '#8888AA',
                              fontSize: '11px',
                              textTransform: 'uppercase',
                              letterSpacing: '1px',
                              marginBottom: '4px',
                            }}
                          >
                            7-Day Projection
                          </div>
                          <div style={{ color: '#5C6BFF', fontSize: '28px', lineHeight: 1.2, fontWeight: 800 }}>
                            $18,643.80
                          </div>
                        </div>
                      </div>
                      <div
                        style={{
                          padding: '16px 24px 24px 24px',
                          color: '#555570',
                          fontSize: '12px',
                          fontStyle: 'italic',
                        }}
                      >
                        Root cause: INVENTORY IMBALANCE
                      </div>
                    </div>

                    <div
                      style={{
                        marginBottom: '14px',
                        border: '1px solid #1E1E35',
                        borderRadius: '8px',
                        overflow: 'hidden',
                      }}
                    >
                      <div style={{ display: 'flex' }}>
                        <div style={{ flex: 1, backgroundColor: '#0D0D2B', padding: '14px 16px' }}>
                          <div
                            style={{
                              color: '#5C6BFF',
                              fontSize: '11px',
                              fontWeight: 700,
                              letterSpacing: '2px',
                              textTransform: 'uppercase',
                              marginBottom: '6px',
                            }}
                          >
                            EXECUTE
                          </div>
                          <div style={{ color: '#5C6BFF', fontSize: '32px', fontWeight: 800 }}>$4,847.20</div>
                          <div style={{ color: '#7B88FF', fontSize: '11px', marginTop: '6px' }}>
                            recovered if you act today
                          </div>
                        </div>
                        <div style={{ flex: 1, backgroundColor: '#2B1515', padding: '14px 16px' }}>
                          <div
                            style={{
                              color: '#FF6B6B',
                              fontSize: '11px',
                              fontWeight: 700,
                              letterSpacing: '2px',
                              textTransform: 'uppercase',
                              marginBottom: '6px',
                            }}
                          >
                            IGNORE
                          </div>
                          <div style={{ color: '#FF6B6B', fontSize: '32px', fontWeight: 800 }}>$2,183.94</div>
                          <div style={{ color: '#FF6B6B', fontSize: '11px', marginTop: '6px' }}>
                            projected 7-day loss
                          </div>
                        </div>
                      </div>
                      <div style={{ padding: '10px 12px', backgroundColor: '#151520', textAlign: 'center' }}>
                        <div style={{ color: '#5C6BFF', fontSize: '14px', fontWeight: 700 }}>DELTA: $2,663.26</div>
                        <div style={{ color: '#555570', fontSize: '11px', marginTop: '3px' }}>
                          You leave this on the table every 7 days you wait
                        </div>
                      </div>
                    </div>

                    {/* ACTION 1 — fully visible */}
                    <div
                      style={{
                        backgroundColor: '#12121E',
                        border: '1px solid #1E1E35',
                        borderLeft: '3px solid #5C6BFF',
                        borderRadius: '6px',
                        padding: '20px',
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'flex-start',
                          gap: '12px',
                          marginBottom: '12px',
                        }}
                      >
                        <div>
                          <div
                            style={{
                              color: '#555570',
                              fontSize: '11px',
                              letterSpacing: '1px',
                              textTransform: 'uppercase',
                              marginBottom: '4px',
                            }}
                          >
                            ACTION 1
                          </div>
                          <div style={{ color: '#5C6BFF', fontSize: '14px', fontWeight: 600 }}>
                            PRIMARY REVENUE LEAK
                          </div>
                        </div>
                        <div
                          style={{
                            display: 'inline-block',
                            padding: '4px 12px',
                            borderRadius: '20px',
                            backgroundColor: '#0D0D2B',
                            color: '#5C6BFF',
                            border: '1px solid #5C6BFF',
                            fontSize: '13px',
                            fontWeight: 700,
                            whiteSpace: 'nowrap',
                          }}
                        >
                          $3,498.12/day
                        </div>
                      </div>
                      <p style={{ color: '#FFFFFF', fontSize: '15px', fontWeight: 600, margin: '0 0 10px 0' }}>
                        2 SKUs have been silent for 90 days — that&apos;s $48,973.65 earning 0% return
                      </p>
                      <p style={{ color: '#8888AA', fontSize: '13px', lineHeight: 1.65, margin: '0 0 16px 0' }}>
                        Dead inventory is not a storage problem, it&apos;s a cash flow problem. Every day these 75 units
                        sit unsold, you&apos;re paying for storage while competitors discount similar products...
                      </p>
                      <div
                        style={{
                          backgroundColor: '#0D0D2B',
                          borderRadius: '4px',
                          padding: '12px 16px',
                          marginBottom: '12px',
                        }}
                      >
                        <p
                          style={{
                            color: '#5C6BFF',
                            fontSize: '10px',
                            letterSpacing: '1px',
                            textTransform: 'uppercase',
                            margin: '0 0 10px 0',
                          }}
                        >
                          WHAT TO DO
                        </p>
                        <p style={{ color: '#5C6BFF', fontSize: '13px', lineHeight: 1.65, margin: '0 0 10px 0' }}>
                          → Create a bundle: pair each dead SKU with your best-selling product at a 10-15% combined
                          discount. Bundling increases AOV while moving dead stock without destroying brand perception.
                        </p>
                        <p style={{ color: '#5C6BFF', fontSize: '13px', lineHeight: 1.65, margin: '0 0 10px 0' }}>
                          → Run a 72-hour flash sale specifically for these 2 SKUs. Scarcity + deadline = action. Email
                          your list with subject line: &quot;We found 75 forgotten items in our warehouse.&quot;
                        </p>
                        <p style={{ color: '#5C6BFF', fontSize: '13px', lineHeight: 1.65, margin: 0 }}>
                          → If units don&apos;t move in 14 days, list them on a secondary channel at cost. Recovering cost
                          beats writing off inventory.
                        </p>
                      </div>
                      <div
                        style={{
                          backgroundColor: '#2B1515',
                          borderRadius: '4px',
                          padding: '10px 14px',
                        }}
                      >
                        <p style={{ color: '#FF6B6B', fontSize: '12px', lineHeight: 1.6, margin: 0 }}>
                          ⚠ At your current AOV of $64.50, you need to sell more orders just to offset what this dead
                          stock is costing you in opportunity. Every week you wait adds to that deficit.
                        </p>
                      </div>
                    </div>

                    {/* ACTION 2 — peek: enough to read the angle, gradient hints more below */}
                    <div
                      style={{
                        position: 'relative',
                        marginTop: '14px',
                        maxHeight: 'clamp(175px, 38vw, 248px)',
                        overflow: 'hidden',
                      }}
                    >
                      <div
                        style={{
                          backgroundColor: '#12121E',
                          border: '1px solid #1E1E35',
                          borderLeft: '3px solid #FF6B6B',
                          borderRadius: '6px',
                          padding: '20px',
                        }}
                      >
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'flex-start',
                            gap: '12px',
                            marginBottom: '12px',
                          }}
                        >
                          <div>
                            <div
                              style={{
                                color: '#555570',
                                fontSize: '11px',
                                letterSpacing: '1px',
                                textTransform: 'uppercase',
                                marginBottom: '4px',
                              }}
                            >
                              ACTION 2
                            </div>
                            <div style={{ color: '#FF6B6B', fontSize: '14px', fontWeight: 600 }}>
                              SECONDARY OPTIMIZATION LEAK
                            </div>
                          </div>
                          <div
                            style={{
                              display: 'inline-block',
                              padding: '4px 12px',
                              borderRadius: '20px',
                              backgroundColor: '#2B1515',
                              color: '#FF6B6B',
                              border: '1px solid #FF6B6B',
                              fontSize: '13px',
                              fontWeight: 700,
                              whiteSpace: 'nowrap',
                            }}
                          >
                            $1,551.91/day
                          </div>
                        </div>
                        <p style={{ color: '#FFFFFF', fontSize: '15px', fontWeight: 600, margin: '0 0 10px 0' }}>
                          5 VIP customers are going quiet — $10,863.36 in lifetime value showing early churn signals
                        </p>
                        <p style={{ color: '#8888AA', fontSize: '13px', lineHeight: 1.65, margin: '0 0 16px 0' }}>
                          They already bought from you; silence now usually means a competitor won the next cart. A
                          short, specific win-back beats another generic discount blast.
                        </p>
                        <div
                          style={{
                            backgroundColor: '#0D0D2B',
                            borderRadius: '4px',
                            padding: '12px 16px',
                            marginBottom: '12px',
                          }}
                        >
                          <p
                            style={{
                              color: '#5C6BFF',
                              fontSize: '10px',
                              letterSpacing: '1px',
                              textTransform: 'uppercase',
                              margin: '0 0 10px 0',
                            }}
                          >
                            WHAT TO DO
                          </p>
                          <p style={{ color: '#5C6BFF', fontSize: '13px', lineHeight: 1.65, margin: '0 0 10px 0' }}>
                            → Send a three-email win-back: Day 1 check-in, Day 4 offer tied to their last purchase, Day
                            10 last chance with a slightly stronger incentive.
                          </p>
                          <p style={{ color: '#5C6BFF', fontSize: '13px', lineHeight: 1.65, margin: '0 0 10px 0' }}>
                            → Segment by last SKU purchased so each VIP sees relevance, not a store-wide coupon they
                            ignore.
                          </p>
                          <p style={{ color: '#5C6BFF', fontSize: '13px', lineHeight: 1.65, margin: 0 }}>
                            → Route anyone who ignores all three into a quarterly touch only — protect deliverability and
                            stop chasing ghosts.
                          </p>
                        </div>
                        <div
                          style={{
                            backgroundColor: '#2B1515',
                            borderRadius: '4px',
                            padding: '10px 14px',
                          }}
                        >
                          <p style={{ color: '#FF6B6B', fontSize: '12px', lineHeight: 1.6, margin: 0 }}>
                            ⚠ Every 30 days without contact, reactivation probability drops sharply — these five are
                            still in the window if you move this week.
                          </p>
                        </div>
                      </div>
                      <div
                        aria-hidden="true"
                        style={{
                          position: 'absolute',
                          bottom: 0,
                          left: 0,
                          right: 0,
                          height: '88px',
                          pointerEvents: 'none',
                          background: 'linear-gradient(to bottom, rgba(8, 8, 15, 0), #08080F)',
                        }}
                      />
                    </div>
                  </div>
                </div>
              </div>
              <div className="lp-device-base" />
            </div>
            <p className="lp-device-caption">This is what lands in your inbox every morning.</p>
          </div>

          <Link className="lp-cta" to="/connect">
            GET MY FREE STORE DIAGNOSIS
          </Link>
          <p className="lp-cta-note">No credit card. No setup. 7-day free trial.</p>
        </section>

        <section className="lp-objections" aria-label="Why Perspicor">
          <ul style={{listStyle:'none',padding:'0',margin:'0 auto',
                      maxWidth:'640px'}}>
            <li style={{display:'flex',alignItems:'flex-start',
                        marginBottom:'28px'}}>
              <span style={{color:'#5C6BFF',fontSize:'20px',
                            marginRight:'14px',marginTop:'2px',
                            flexShrink:0}}>◆</span>
              <p style={{margin:0,fontSize:'16px',lineHeight:'1.8'}}>
                <strong style={{color:'#FFFFFF',fontWeight:700}}>
                  Most Shopify apps show you numbers.
                </strong>
                <span style={{color:'#8888AA'}}>
                  {' '}— Perspicor tells you exactly what to fix, 
                  and what it costs you every day you don't.
                </span>
              </p>
            </li>
            <li style={{display:'flex',alignItems:'flex-start',
                        marginBottom:'28px'}}>
              <span style={{color:'#5C6BFF',fontSize:'20px',
                            marginRight:'14px',marginTop:'2px',
                            flexShrink:0}}>◆</span>
              <p style={{margin:0,fontSize:'16px',lineHeight:'1.8'}}>
                <strong style={{color:'#FFFFFF',fontWeight:700}}>
                  Connect in 60 seconds.
                </strong>
                <span style={{color:'#8888AA'}}>
                  {' '}— No setup, no spreadsheets, no consultants. 
                  Your first diagnosis arrives the next morning.
                </span>
              </p>
            </li>
            <li style={{display:'flex',alignItems:'flex-start',
                        marginBottom:'0'}}>
              <span style={{color:'#5C6BFF',fontSize:'20px',
                            marginRight:'14px',marginTop:'2px',
                            flexShrink:0}}>◆</span>
              <p style={{margin:0,fontSize:'16px',lineHeight:'1.8'}}>
                <strong style={{color:'#FFFFFF',fontWeight:700}}>
                  Every action comes with a dollar figure.
                </strong>
                <span style={{color:'#8888AA'}}>
                  {' '}— Dead inventory, silent VIP customers, 
                  abandoned checkouts — you see the exact cost 
                  of ignoring each one.
                </span>
              </p>
            </li>
          </ul>
        </section>
      </main>

      <footer className="lp-footer">
        <p className="lp-legal">© 2026 Perspicor. All rights reserved.</p>
      </footer>
    </div>
  )
}

function ConnectPage() {
  const [email, setEmail] = useState('')
  const [shop, setShop] = useState('')
  const [error, setError] = useState('')

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalized = normalizeShopDomain(shop)
    if (!normalized) {
      setError('Enter your Shopify store URL.')
      return
    }
    if (!normalized.includes('.')) {
      setError('Use your full store domain (e.g. your-store.myshopify.com).')
      return
    }
    setError('')
    const base = apiBaseUrl()
    if (!base) {
      setError('Configuration error: API URL is not set.')
      return
    }
    window.location.href = `${base}/oauth/install?shop=${encodeURIComponent(normalized)}&email=${encodeURIComponent(email.trim())}`
  }

  return (
    <div className="connect-shell">
      <SiteHeader />
      <main className="connect-main">
        <form className="connect-form" onSubmit={handleSubmit} noValidate>
          <label className="connect-label" htmlFor="contact-email">
            Where should we send your daily report?
          </label>
          <input
            id="contact-email"
            className="connect-input"
            type="email"
            name="email"
            autoComplete="email"
            placeholder="your@email.com"
            required
            value={email}
            onChange={(e) => {
              setEmail(e.target.value)
            }}
          />
          <label className="connect-label" htmlFor="shop-domain">
            Your Shopify store URL
          </label>
          <input
            id="shop-domain"
            className="connect-input"
            type="text"
            name="shop"
            autoComplete="url"
            placeholder="your-store.myshopify.com"
            required
            value={shop}
            onChange={(e) => {
              setShop(e.target.value)
              if (error) {
                setError('')
              }
            }}
          />
          {error ? <p className="connect-error">{error}</p> : null}
          <button type="submit" className="lp-cta connect-submit">
            Connect &amp; Get Free Diagnosis
          </button>
          <p className="connect-foot">No credit card required</p>
        </form>
      </main>
    </div>
  )
}

function SuccessPage() {
  return (
    <div className="success-shell">
      <SiteHeader />
      <main className="success-main">
        <h1 className="success-title">Your store is connected!</h1>
        <p className="success-sub">
          Data is being synced now. Your first Perspicor diagnosis will arrive in your inbox shortly.
        </p>
      </main>
    </div>
  )
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/connect" element={<ConnectPage />} />
      <Route path="/success" element={<SuccessPage />} />
      <Route path="/check-your-email" element={<Navigate to="/success" replace />} />
    </Routes>
  )
}

export default App
