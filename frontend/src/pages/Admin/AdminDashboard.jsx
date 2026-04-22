import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { adminApi } from '../../api/client'
import styles from './AdminDashboard.module.css'

function StatCard({ label, value, sub, accent }) {
  return (
    <div className={styles.statCard} style={accent ? { borderTop: `3px solid ${accent}` } : {}}>
      <span className={styles.statValue}>{value ?? '—'}</span>
      <span className={styles.statLabel}>{label}</span>
      {sub && <span className={styles.statSub}>{sub}</span>}
    </div>
  )
}

export default function AdminDashboard() {
  const navigate = useNavigate()
  const [stats, setStats]   = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    adminApi.stats()
      .then(r => setStats(r.data))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className={styles.loading}>Loading stats…</div>
  if (!stats)  return <div className={styles.loading}>Failed to load stats.</div>

  const { users, documents, analyses } = stats
  const completed = documents.by_status?.completed || 0
  const failed    = documents.by_status?.failed    || 0
  const processing = documents.by_status?.processing || 0
  const successRate = documents.total > 0
    ? Math.round((completed / documents.total) * 100)
    : 0

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1 className={styles.title}>Overview</h1>
        <p className={styles.sub}>System-wide usage statistics</p>
      </div>

      <div className={styles.statsGrid}>
        <StatCard label="Total Users"     value={users.total}          accent="var(--accent)"   />
        <StatCard label="Total Documents" value={documents.total}      accent="#8B5CF6"         />
        <StatCard label="Analyses Done"   value={analyses.total}       accent="var(--success)"  />
        <StatCard label="Success Rate"    value={`${successRate}%`}    accent="var(--warning)"  />
      </div>

      <div className={styles.gridTwo}>
        <div className={styles.card}>
          <h3 className={styles.cardTitle}>Document Status</h3>
          <div className={styles.statusList}>
            {[
              { label: 'Completed',  val: completed,  color: 'var(--success)' },
              { label: 'Processing', val: processing, color: 'var(--warning)' },
              { label: 'Failed',     val: failed,     color: 'var(--danger)'  },
              { label: 'Uploaded',   val: documents.by_status?.uploaded || 0, color: 'var(--text-muted)' },
            ].map(s => (
              <div key={s.label} className={styles.statusRow}>
                <div className={styles.statusDot} style={{ background: s.color }} />
                <span className={styles.statusLabel}>{s.label}</span>
                <span className={styles.statusVal}>{s.val}</span>
                <div className={styles.statusBarTrack}>
                  <div
                    className={styles.statusBarFill}
                    style={{
                      width: documents.total ? `${(s.val / documents.total) * 100}%` : '0%',
                      background: s.color,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className={styles.card}>
          <h3 className={styles.cardTitle}>Risk Distribution</h3>
          <div className={styles.riskList}>
            {[
              { label: 'Low risk',    key: 'low',    color: 'var(--risk-low)'    },
              { label: 'Medium risk', key: 'medium', color: 'var(--risk-medium)' },
              { label: 'High risk',   key: 'high',   color: 'var(--risk-high)'   },
            ].map(r => {
              const val = analyses.by_risk_score?.[r.key] || 0
              const pct = analyses.total ? Math.round((val / analyses.total) * 100) : 0
              return (
                <div key={r.key} className={styles.statusRow}>
                  <div className={styles.statusDot} style={{ background: r.color }} />
                  <span className={styles.statusLabel}>{r.label}</span>
                  <span className={styles.statusVal}>{val}</span>
                  <div className={styles.statusBarTrack}>
                    <div className={styles.statusBarFill} style={{ width: `${pct}%`, background: r.color }} />
                  </div>
                </div>
              )
            })}
          </div>

          <div className={styles.divider} />

          <div className={styles.perf}>
            <div className={styles.perfItem}>
              <span className={styles.perfVal}>{analyses.avg_tokens_used?.toFixed(0) || 0}</span>
              <span className={styles.perfLabel}>Avg tokens / analysis</span>
            </div>
            <div className={styles.perfItem}>
              <span className={styles.perfVal}>{analyses.avg_processing_seconds?.toFixed(1) || 0}s</span>
              <span className={styles.perfLabel}>Avg processing time</span>
            </div>
          </div>
        </div>
      </div>

      <div className={styles.quickActions}>
        <h3 className={styles.cardTitle}>Quick Actions</h3>
        <div className={styles.actionBtns}>
          <button className={styles.actionBtn} onClick={() => navigate('/admin/users')}>
            <span>👥</span> Manage Users
          </button>
          <button className={styles.actionBtn} onClick={() => navigate('/admin/documents')}>
            <span>📄</span> View Documents
          </button>
          <button className={styles.actionBtn} onClick={() => navigate('/admin/documents?status=failed')}>
            <span>⚠</span> Failed Documents
          </button>
        </div>
      </div>
    </div>
  )
}