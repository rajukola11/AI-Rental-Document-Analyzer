import { useState, useEffect } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { documentsApi } from '../../api/client'
import { useToast } from '../../components/ui/Toast'
import styles from './Analysis.module.css'

const RISK_META = {
  low:    { label: 'Low Risk',    bg: 'var(--success-light)', color: 'var(--risk-low)',    bar: '#16A34A' },
  medium: { label: 'Medium Risk', bg: 'var(--warning-light)', color: 'var(--risk-medium)', bar: '#D97706' },
  high:   { label: 'High Risk',   bg: 'var(--danger-light)',  color: 'var(--risk-high)',   bar: '#DC2626' },
}

const RISK_SCORE = { low: 33, medium: 66, high: 100 }

export default function Analysis() {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const [searchParams] = useSearchParams()
  const [doc, setDoc]         = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')
  const [activeTab, setActiveTab] = useState('summary')
  const [keeping, setKeeping]   = useState(false)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    documentsApi.get(id)
      .then(r => setDoc(r.data))
      .catch(() => setError('Document not found.'))
      .finally(() => setLoading(false))
  }, [id])

  // Auto-trigger keep if redirected from email link (?keep=1)
  useEffect(() => {
    if (doc && searchParams.get('keep') === '1' && !doc.is_deleted) {
      handleKeep()
    }
  }, [doc])

  const handleKeep = async () => {
    setKeeping(true)
    try {
      const r = await documentsApi.keep(id)
      toast.success(`Document kept until ${new Date(r.data.expires_at).toLocaleDateString()}`)
      setDoc(prev => ({ ...prev, expires_at: r.data.expires_at }))
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to extend document.')
    } finally {
      setKeeping(false)
    }
  }

  const handleDelete = async () => {
    if (!window.confirm(`Delete "${doc?.original_filename}"? This cannot be undone.`)) return
    setDeleting(true)
    try {
      await documentsApi.delete(id)
      toast.success('Document deleted.')
      navigate('/dashboard')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Delete failed.')
      setDeleting(false)
    }
  }

  if (loading) return <div className={styles.loading}><span className={styles.spinner} />Loading analysis…</div>
  if (error)   return <div className={styles.errorPage}><p>{error}</p><button onClick={() => navigate('/dashboard')}>← Back</button></div>
  if (!doc)    return null

  const a = doc.analysis
  const risk = a ? RISK_META[a.risk_score] || RISK_META.medium : null

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <button className={styles.backBtn} onClick={() => navigate('/dashboard')}>← Back</button>
        <div style={{ flex: 1 }}>
          <h1 className={styles.title}>{doc.original_filename}</h1>
          <p className={styles.meta}>
            Uploaded {new Date(doc.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}
            {a && <> · {a.tokens_used} tokens · {a.processing_time_seconds}s</>}
            {doc.expires_at && !doc.is_deleted && (
              <> · <span style={{ color: 'var(--warning)' }}>
                Deletes {new Date(doc.expires_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
              </span></>
            )}
          </p>
        </div>
        {!doc.is_deleted && (
          <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
            <button className={styles.keepBtn} onClick={handleKeep} disabled={keeping}>
              {keeping ? 'Extending…' : '📌 Keep 3 more days'}
            </button>
            <button className={styles.deleteBtn} onClick={handleDelete} disabled={deleting}>
              {deleting ? '…' : '🗑 Delete'}
            </button>
          </div>
        )}
      </div>

      {!a ? (
        <div className={styles.processing}>
          <span className={styles.bigSpinner} />
          <h3>Analysis in progress</h3>
          <p>Your contract is being analyzed. This usually takes 10–30 seconds.</p>
          <button className={styles.refreshBtn} onClick={() => window.location.reload()}>Refresh</button>
        </div>
      ) : (
        <>
          {/* Risk score card */}
          <div className={styles.riskCard} style={{ background: risk.bg }}>
            <div className={styles.riskLeft}>
              <span className={styles.riskLabel} style={{ color: risk.color }}>{risk.label}</span>
              <div className={styles.riskBar}>
                <div className={styles.riskFill} style={{ width: `${RISK_SCORE[a.risk_score]}%`, background: risk.bar }} />
              </div>
            </div>
            <div className={styles.riskStats}>
              <div className={styles.stat}>
                <span className={styles.statVal}>{a.clauses?.length || 0}</span>
                <span className={styles.statLabel}>Clauses</span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statVal}>{a.risks?.length || 0}</span>
                <span className={styles.statLabel}>Risks</span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statVal}>{a.model_used || 'GPT'}</span>
                <span className={styles.statLabel}>Model</span>
              </div>
            </div>
          </div>

          {/* Tabs */}
          <div className={styles.tabs}>
            {['summary', 'clauses', 'risks'].map(t => (
              <button
                key={t}
                className={`${styles.tab} ${activeTab === t ? styles.activeTab : ''}`}
                onClick={() => setActiveTab(t)}
              >
                {t.charAt(0).toUpperCase() + t.slice(1)}
                {t === 'clauses' && <span className={styles.tabCount}>{a.clauses?.length}</span>}
                {t === 'risks'   && <span className={styles.tabCount}>{a.risks?.length}</span>}
              </button>
            ))}
          </div>

          <div className={styles.tabContent}>
            {activeTab === 'summary' && (
              <div className={styles.summaryCard}>
                <h3 className={styles.sectionTitle}>Contract Summary</h3>
                <p className={styles.summaryText}>{a.summary}</p>
              </div>
            )}

            {activeTab === 'clauses' && (
              <div className={styles.clauseList}>
                {a.clauses?.map((c, i) => (
                  <div key={i} className={styles.clauseCard}>
                    <div className={styles.clauseHeader}>
                      <span className={styles.clauseType}>{c.type}</span>
                    </div>
                    {c.text && (
                      <div className={styles.clauseOriginal}>
                        <span className={styles.clauseOriginalLabel}>Original text</span>
                        <p className={styles.clauseOriginalText}>{c.text}</p>
                      </div>
                    )}
                    <div className={styles.clauseExplanation}>
                      <span className={styles.clauseExplainLabel}>What this means</span>
                      <p>{c.explanation}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {activeTab === 'risks' && (
              <div className={styles.riskList}>
                {a.risks?.length === 0 ? (
                  <div className={styles.noRisks}>
                    <span>✓</span>
                    <p>No significant risks detected in this contract.</p>
                  </div>
                ) : (
                  a.risks?.map((r, i) => (
                    <div key={i} className={styles.riskItem}>
                      <span className={styles.riskItemIcon}>⚠</span>
                      <p>{r}</p>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}