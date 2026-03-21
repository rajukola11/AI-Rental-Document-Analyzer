import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { documentsApi } from '../../api/client'
import { useToast } from '../../components/ui/Toast'
import api from '../../api/client'
import styles from './Billing.module.css'

const PACKAGES = [
  { credits: 1,  amount_cents: 300,  label: '1 analysis',  price: '€3.00',  save: null,    popular: false },
  { credits: 5,  amount_cents: 1200, label: '5 analyses',  price: '€12.00', save: 'Save 20%', popular: true },
  { credits: 10, amount_cents: 2000, label: '10 analyses', price: '€20.00', save: 'Save 33%', popular: false },
]

export default function Billing() {
  const [searchParams] = useSearchParams()
  const toast = useToast()
  const [billing, setBilling]   = useState(null)
  const [history, setHistory]   = useState([])
  const [loading, setLoading]   = useState(true)
  const [buying, setBuying]     = useState(null)

  useEffect(() => {
    if (searchParams.get('success') === 'true') {
      toast.success('Payment successful! Credits added to your account.')
    }
    if (searchParams.get('cancelled') === 'true') {
      toast.info('Payment cancelled.')
    }
    loadData()
  }, [])

  const loadData = async () => {
    try {
      const [b, h] = await Promise.all([
        api.get('/payments/billing'),
        api.get('/payments/history'),
      ])
      setBilling(b.data)
      setHistory(h.data)
    } catch (e) {
      toast.error('Failed to load billing info.')
    } finally {
      setLoading(false)
    }
  }

  const purchase = async (pkg) => {
    setBuying(pkg.credits)
    try {
      const r = await api.post('/payments/checkout', { credits: pkg.credits })
      window.location.href = r.data.checkout_url
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to start checkout.')
      setBuying(null)
    }
  }

  if (loading) return <div className={styles.loading}>Loading billing info…</div>

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1 className={styles.title}>Billing</h1>
        <p className={styles.sub}>Manage your analyses and purchase credits</p>
      </div>

      {/* Usage card */}
      <div className={styles.usageCard}>
        <div className={styles.usageStat}>
          <span className={styles.usageVal}>{billing?.free_uploads_remaining}</span>
          <span className={styles.usageLabel}>Free analyses left</span>
        </div>
        <div className={styles.usageDivider} />
        <div className={styles.usageStat}>
          <span className={styles.usageVal}>{billing?.upload_credits}</span>
          <span className={styles.usageLabel}>Paid credits</span>
        </div>
        <div className={styles.usageDivider} />
        <div className={styles.usageStat}>
          <span className={styles.usageVal}>{billing?.uploads_used}</span>
          <span className={styles.usageLabel}>Total analyses done</span>
        </div>
        <div className={styles.usageRight}>
          {billing?.can_upload ? (
            <span className={styles.canUpload}>✓ Ready to analyze</span>
          ) : (
            <span className={styles.cantUpload}>Purchase credits to continue</span>
          )}
        </div>
      </div>

      {/* Pricing packages */}
      <div className={styles.sectionTitle}>Purchase credits</div>
      <div className={styles.packages}>
        {PACKAGES.map(pkg => (
          <div key={pkg.credits} className={`${styles.packageCard} ${pkg.popular ? styles.popular : ''}`}>
            {pkg.popular && <div className={styles.popularBadge}>Most popular</div>}
            <div className={styles.packageCredits}>{pkg.credits}</div>
            <div className={styles.packageLabel}>{pkg.label}</div>
            <div className={styles.packagePrice}>{pkg.price}</div>
            {pkg.save && <div className={styles.packageSave}>{pkg.save}</div>}
            <div className={styles.packagePer}>
              €{(pkg.amount_cents / pkg.credits / 100).toFixed(2)} per analysis
            </div>
            <button
              className={styles.buyBtn}
              onClick={() => purchase(pkg)}
              disabled={buying === pkg.credits}
            >
              {buying === pkg.credits ? (
                <><span className={styles.spinner} />Redirecting…</>
              ) : 'Buy now'}
            </button>
          </div>
        ))}
      </div>

      {/* Payment history */}
      {history.length > 0 && (
        <>
          <div className={styles.sectionTitle}>Payment history</div>
          <div className={styles.historyTable}>
            <div className={styles.historyHeader}>
              <span>Date</span>
              <span>Credits</span>
              <span>Amount</span>
              <span>Status</span>
            </div>
            {history.map(p => (
              <div key={p.id} className={styles.historyRow}>
                <span className={styles.historyDate}>
                  {new Date(p.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}
                </span>
                <span>{p.credits} {p.credits === 1 ? 'credit' : 'credits'}</span>
                <span>€{(p.amount_cents / 100).toFixed(2)}</span>
                <span className={styles.statusPaid}>Paid</span>
              </div>
            ))}
          </div>
        </>
      )}

      <div className={styles.note}>
        Payments are processed securely by Stripe. We never store your card details.
      </div>
    </div>
  )
}
