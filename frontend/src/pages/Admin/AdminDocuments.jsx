import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { adminApi } from '../../api/client'
import styles from './AdminDocuments.module.css'

const STATUSES = ['', 'uploaded', 'processing', 'completed', 'failed']

const STATUS_META = {
  uploaded:   { label: 'Queued',    color: 'var(--text-muted)',  bg: 'var(--surface-2)' },
  processing: { label: 'Analyzing', color: 'var(--warning)',     bg: 'var(--warning-light)' },
  completed:  { label: 'Completed', color: 'var(--success)',     bg: 'var(--success-light)' },
  failed:     { label: 'Failed',    color: 'var(--danger)',      bg: 'var(--danger-light)' },
}

const RISK_COLOR = { low: 'var(--risk-low)', medium: 'var(--risk-medium)', high: 'var(--risk-high)' }

export default function AdminDocuments() {
  const navigate = useNavigate()
  const [docs, setDocs]       = useState([])
  const [total, setTotal]     = useState(0)
  const [page, setPage]       = useState(1)
  const [status, setStatus]   = useState('')
  const [loading, setLoading] = useState(true)

  const load = (p = 1, s = status) => {
    setLoading(true)
    adminApi.documents(p, s)
      .then(r => {
        setDocs(r.data.items)
        setTotal(r.data.total)
        setPage(p)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { load(1, status) }, [status])

  const totalPages = Math.ceil(total / 50)

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.title}>Documents</h1>
          <p className={styles.sub}>{total} total documents</p>
        </div>
        <div className={styles.filters}>
          {STATUSES.map(s => (
            <button
              key={s || 'all'}
              className={`${styles.filterBtn} ${status === s ? styles.filterActive : ''}`}
              onClick={() => setStatus(s)}
            >
              {s || 'All'}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className={styles.loading}>Loading documents…</div>
      ) : docs.length === 0 ? (
        <div className={styles.empty}>No documents found.</div>
      ) : (
        <>
          <div className={styles.table}>
            <div className={styles.thead}>
              <div className={styles.tr}>
                <div className={styles.th} style={{ flex: 3 }}>File</div>
                <div className={styles.th} style={{ flex: 2 }}>User ID</div>
                <div className={styles.th} style={{ flex: 1 }}>Status</div>
                <div className={styles.th} style={{ flex: 1 }}>Risk</div>
                <div className={styles.th} style={{ flex: 1 }}>Date</div>
                <div className={styles.th} style={{ flex: 1 }}>Action</div>
              </div>
            </div>
            <div className={styles.tbody}>
              {docs.map(doc => {
                const sm = STATUS_META[doc.status] || STATUS_META.uploaded
                return (
                  <div key={doc.id} className={styles.tr}>
                    <div className={styles.td} style={{ flex: 3 }}>
                      <div className={styles.fileCell}>
                        <span className={styles.fileIcon}>
                          {doc.original_filename?.endsWith('.pdf') ? '📄' : '📝'}
                        </span>
                        <div>
                          <div className={styles.filename}>{doc.original_filename}</div>
                          <div className={styles.docId}>{doc.id}</div>
                        </div>
                      </div>
                    </div>
                    <div className={styles.td} style={{ flex: 2 }}>
                      <span className={styles.mono}>{String(doc.user_id).slice(0, 8)}…</span>
                    </div>
                    <div className={styles.td} style={{ flex: 1 }}>
                      <span className={styles.badge} style={{ color: sm.color, background: sm.bg }}>
                        {sm.label}
                      </span>
                    </div>
                    <div className={styles.td} style={{ flex: 1 }}>
                      {doc.analysis?.risk_score && (
                        <span className={styles.risk} style={{ color: RISK_COLOR[doc.analysis.risk_score] }}>
                          {doc.analysis.risk_score}
                        </span>
                      )}
                    </div>
                    <div className={styles.td} style={{ flex: 1 }}>
                      <span className={styles.date}>
                        {new Date(doc.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
                      </span>
                    </div>
                    <div className={styles.td} style={{ flex: 1 }}>
                      {doc.status === 'completed' && (
                        <button
                          className={styles.viewBtn}
                          onClick={() => navigate(`/documents/${doc.id}`)}
                        >
                          View
                        </button>
                      )}
                      {doc.status === 'failed' && doc.error_message && (
                        <span className={styles.errorHint} title={doc.error_message}>⚠ Error</span>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {totalPages > 1 && (
            <div className={styles.pagination}>
              <button disabled={page === 1} onClick={() => load(page - 1)} className={styles.pageBtn}>← Prev</button>
              <span className={styles.pageInfo}>Page {page} of {totalPages}</span>
              <button disabled={page === totalPages} onClick={() => load(page + 1)} className={styles.pageBtn}>Next →</button>
            </div>
          )}
        </>
      )}
    </div>
  )
}