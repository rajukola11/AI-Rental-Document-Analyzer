import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import styles from './LandingPage.module.css'

const features = [
  {
    icon: '⚡',
    title: 'Instant Analysis',
    desc: 'Upload your German rental contract and get a full breakdown in under 60 seconds.',
  },
  {
    icon: '🔍',
    title: 'Risk Detection',
    desc: 'We flag unusual clauses, hidden fees, and tenant-unfriendly terms so nothing slips by.',
  },
  {
    icon: '🌐',
    title: 'Plain English',
    desc: 'Dense legal German translated into clear, simple summaries anyone can understand.',
  },
  {
    icon: '🔒',
    title: 'Secure Storage',
    desc: 'Your documents are encrypted at rest and never shared with third parties.',
  },
]

const steps = [
  { num: '01', title: 'Upload your contract', desc: 'PDF or image — we handle it all.' },
  { num: '02', title: 'AI reads every clause', desc: 'Our model parses each section in seconds.' },
  { num: '03', title: 'Get your report', desc: 'Clear summary, risks highlighted, questions answered.' },
]

export default function LandingPage() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <div className={styles.root}>
      {/* ── NAV ── */}
      <header className={`${styles.nav} ${scrolled ? styles.navScrolled : ''}`}>
        <div className={styles.navInner}>
          <div className={styles.logo}>
            <span className={styles.logoMark}>RA</span>
            <span className={styles.logoText}>RentalAI</span>
          </div>

          {/* Desktop nav links */}
          <nav className={styles.navLinks}>
            <a href="#features" className={styles.navLink}>Features</a>
            <a href="#how" className={styles.navLink}>How it works</a>
            <a href="#pricing" className={styles.navLink}>Pricing</a>
          </nav>

          {/* Desktop CTA */}
          <div className={styles.navCta}>
            <Link to="/login" className={styles.navBtnOutline}>Log in</Link>
            <Link to="/register" className={styles.navBtnFill}>Get started</Link>
          </div>

          {/* Hamburger */}
          <button
            className={`${styles.hamburger} ${menuOpen ? styles.hamburgerOpen : ''}`}
            onClick={() => setMenuOpen(o => !o)}
            aria-label="Toggle menu"
          >
            <span /><span /><span />
          </button>
        </div>

        {/* Mobile menu */}
        <div className={`${styles.mobileMenu} ${menuOpen ? styles.mobileMenuOpen : ''}`}>
          <a href="#features" className={styles.mobileLink} onClick={() => setMenuOpen(false)}>Features</a>
          <a href="#how" className={styles.mobileLink} onClick={() => setMenuOpen(false)}>How it works</a>
          <a href="#pricing" className={styles.mobileLink} onClick={() => setMenuOpen(false)}>Pricing</a>
          <div className={styles.mobileDivider} />
          <Link to="/login" className={styles.mobileLinkBold} onClick={() => setMenuOpen(false)}>Log in</Link>
          <Link to="/register" className={`${styles.mobileLinkBold} ${styles.mobileLinkFill}`} onClick={() => setMenuOpen(false)}>Register</Link>
        </div>
      </header>

      {/* ── HERO ── */}
      <section className={styles.hero}>
        <div className={styles.heroBg}>
          <div className={styles.heroBgBlob1} />
          <div className={styles.heroBgBlob2} />
          <div className={styles.heroBgGrid} />
        </div>
        <div className={styles.heroContent}>
          <div className={styles.heroBadge}>
            <span className={styles.heroBadgeDot} />
            AI-powered · German rental law expertise
          </div>
          <h1 className={styles.heroTitle}>
            Understand your<br />
            <span className={styles.heroTitleAccent}>rental contract</span><br />
            in minutes
          </h1>
          <p className={styles.heroSub}>
            Stop guessing what you're signing. RentalAI reads your German rental contract,
            flags risky clauses, and explains everything in plain English.
          </p>
          <div className={styles.heroCta}>
            <Link to="/register" className={styles.ctaPrimary}>
              Analyze my contract
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </Link>
            <Link to="/login" className={styles.ctaSecondary}>Sign in</Link>
          </div>
          <p className={styles.heroNote}>Free to try · No credit card required</p>
        </div>

        {/* Mock document card */}
        <div className={styles.heroVisual}>
          <div className={styles.mockCard}>
            <div className={styles.mockCardHeader}>
              <div className={styles.mockCardDots}>
                <span /><span /><span />
              </div>
              <span className={styles.mockCardTitle}>Mietvertrag_2024.pdf</span>
              <span className={styles.mockCardBadge}>Analyzed</span>
            </div>
            <div className={styles.mockCardBody}>
              <div className={styles.mockRow}>
                <span className={styles.mockLabel}>Risk Score</span>
                <div className={styles.mockRiskBar}>
                  <div className={styles.mockRiskFill} style={{ width: '35%' }} />
                </div>
                <span className={styles.mockRiskText}>Low</span>
              </div>
              <div className={styles.mockSection}>
                <div className={`${styles.mockFlag} ${styles.mockFlagOk}`}>
                  <span>✓</span> Standard deposit clause (3 months)
                </div>
                <div className={`${styles.mockFlag} ${styles.mockFlagWarn}`}>
                  <span>⚠</span> Renovation obligation — review carefully
                </div>
                <div className={`${styles.mockFlag} ${styles.mockFlagOk}`}>
                  <span>✓</span> Notice period: 3 months (legal minimum)
                </div>
                <div className={`${styles.mockFlag} ${styles.mockFlagOk}`}>
                  <span>✓</span> Rent increase cap within legal limits
                </div>
              </div>
              <div className={styles.mockSummaryLabel}>AI Summary</div>
              <div className={styles.mockSummaryLines}>
                <div className={styles.mockLine} style={{ width: '92%' }} />
                <div className={styles.mockLine} style={{ width: '78%' }} />
                <div className={styles.mockLine} style={{ width: '85%' }} />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── FEATURES ── */}
      <section id="features" className={styles.features}>
        <div className={styles.container}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionTag}>Features</span>
            <h2 className={styles.sectionTitle}>Everything you need to rent with confidence</h2>
            <p className={styles.sectionSub}>No legal degree required.</p>
          </div>
          <div className={styles.featureGrid}>
            {features.map(f => (
              <div key={f.title} className={styles.featureCard}>
                <div className={styles.featureIcon}>{f.icon}</div>
                <h3 className={styles.featureTitle}>{f.title}</h3>
                <p className={styles.featureDesc}>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section id="how" className={styles.how}>
        <div className={styles.container}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionTag}>How it works</span>
            <h2 className={styles.sectionTitle}>Three steps to clarity</h2>
          </div>
          <div className={styles.steps}>
            {steps.map((s, i) => (
              <div key={s.num} className={styles.step}>
                <div className={styles.stepNum}>{s.num}</div>
                {i < steps.length - 1 && <div className={styles.stepLine} />}
                <h3 className={styles.stepTitle}>{s.title}</h3>
                <p className={styles.stepDesc}>{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── PRICING ── */}
      <section id="pricing" className={styles.pricing}>
        <div className={styles.container}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionTag}>Pricing</span>
            <h2 className={styles.sectionTitle}>Simple, honest pricing</h2>
            <p className={styles.sectionSub}>Start free. Pay only when you need more.</p>
          </div>

          {/* Free plan highlight */}
          <div className={styles.freePlanBanner}>
            <span className={styles.freePlanEmoji}>🆓</span>
            <div>
              <div className={styles.freePlanTitle}>Free Plan — every account gets 2 analyses</div>
              <div className={styles.freePlanSub}>No credit card required. Try it before you pay anything.</div>
            </div>
          </div>

          <div className={styles.pricingGrid}>
            {/* Pay-as-you-go */}
            <div className={styles.pricingCard}>
              <div className={styles.pricingName}>💳 Pay-As-You-Go</div>
              <div className={styles.pricingPrice}>€1<span>/analysis</span></div>
              <div className={styles.pricingDesc}>Top up one at a time, no commitment.</div>
              <ul className={styles.pricingList}>
                <li>1 analysis = €1.00</li>
                <li>No expiry on credits</li>
                <li>Full risk report</li>
              </ul>
              <Link to="/register" className={styles.pricingBtn}>Get started</Link>
            </div>

            {/* Most Popular */}
            <div className={`${styles.pricingCard} ${styles.pricingCardPro}`}>
              <div className={styles.pricingProBadge}>🔥 Most popular</div>
              <div className={styles.pricingName}>Starter Pack</div>
              <div className={styles.pricingPrice}>€4<span>/pack</span></div>
              <div className={styles.pricingDesc}>Best for renters signing a new lease.</div>
              <ul className={styles.pricingList}>
                <li>6 analyses included</li>
                <li className={styles.pricingListBonus}>🎁 +1 bonus on first purchase</li>
                <li>→ 7 analyses total</li>
                <li>~€0.57 per analysis</li>
                <li className={styles.pricingListSave}>💚 Save 43%</li>
              </ul>
              <Link to="/register" className={styles.pricingBtnPro}>Get 7 analyses →</Link>
            </div>

            {/* Best Value */}
            <div className={`${styles.pricingCard} ${styles.pricingCardBest}`}>
              <div className={styles.pricingBestBadge}>🚀 Best value</div>
              <div className={styles.pricingName}>Pro Pack</div>
              <div className={styles.pricingPrice}>€10<span>/pack</span></div>
              <div className={styles.pricingDesc}>For landlords or frequent movers.</div>
              <ul className={styles.pricingList}>
                <li>20 analyses included</li>
                <li className={styles.pricingListBonus}>🎁 +3 bonus on first purchase</li>
                <li>→ 23 analyses total</li>
                <li>~€0.43 per analysis</li>
                <li className={styles.pricingListSave}>💚 Save 57%</li>
              </ul>
              <Link to="/register" className={styles.pricingBtnBest}>Get 23 analyses →</Link>
            </div>
          </div>
        </div>
      </section>

      {/* ── CTA BANNER ── */}
      <section className={styles.ctaBanner}>
        <div className={styles.container}>
          <h2 className={styles.ctaBannerTitle}>Ready to read the fine print?</h2>
          <p className={styles.ctaBannerSub}>Join thousands of tenants who signed with confidence.</p>
          <div className={styles.ctaBannerBtns}>
            <Link to="/register" className={styles.ctaPrimary}>Create free account</Link>
            <Link to="/login" className={`${styles.ctaSecondary} ${styles.ctaSecondaryLight}`}>Log in</Link>
          </div>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <div className={styles.logo}>
            <span className={styles.logoMark}>RA</span>
            <span className={styles.logoText}>RentalAI</span>
          </div>
          <p className={styles.footerNote}>© {new Date().getFullYear()} RentalAI. Not legal advice.</p>
          <div className={styles.footerLinks}>
            <Link to="/login">Log in</Link>
            <Link to="/register">Register</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}