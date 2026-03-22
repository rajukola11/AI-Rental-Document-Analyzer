import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { documentsApi } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import { useToast } from '../../components/ui/Toast'
import { SkeletonTable } from '../../components/ui/Skeleton'
import VerificationBanner from '../../components/ui/VerificationBanner'
import styles from './Dashboard.module.css'

const STATUS_META = {
  uploaded:   { label: 'Queued',    color: 'var(--text-muted)',  bg: 'var(--surface-2)' },
  processing: { label: 'Analyzing', color: 'var(--warning)',     bg: 'var(--warning-light)' },
  completed:  { label: 'Completed', color: 'var(--success)',     bg: 'var(--success-light)' },
  failed:     { label: 'Failed',    color: 'var(--danger)',      bg: 'var(--danger-light)' },
}

const RISK_META = {
  low:    { label: 'Low risk',    color: 'var(--risk-low)'    },
  medium: { label: 'Medium risk', color: 'var(--risk-medium)' },
  high:   { label: 'High risk',   color: 'var(--risk-high)'   },
}

function StatusBadge({ status }) {
  const m = STATUS_META[status] || STATUS_META.uploaded
  return (
    <span className={styles.badge} style={{ color: m.color, background: m.bg }}>
      {status === 'processing' && <span className={styles.pulse} />}
      {m.label}
    </span>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const navigate  = useNavigate()
  const toast     = useToast()
  const [docs, setDocs]       = useState([])
  const [total, setTotal]     = useState(0)
  const [page, setPage]       = useState(1)
  const [loading, setLoading] = useState(true)

  const load = async (p = 1) => {
    if (p === 1) setLoading(true)
    try {
      const r = await documentsApi.list(p, 10)
      setDocs(r.data.items)
      setTotal(r.data.total)
      setPage(p)
    } catch {
      toast.error('Failed to load documents.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  useEffect(() => {
    const hasProcessing = docs.some(d => d.status === 'processing' || d.status === 'uploaded')
    if (!hasProcessing) return
    const t = setInterval(async () => {
      try {
        const r = await documentsApi.list(page, 10)
        const newDocs = r.data.items
        const justCompleted = newDocs.filter(nd =>
          nd.status === 'completed' &&
          docs.find(od => od.id === nd.id)?.status !== 'completed'
        )
        justCompleted.forEach(d =>
          toast.success(`Analysis complete: ${d.original_filename}`)
        )
        setDocs(newDocs)
        setTotal(r.data.total)
      } catch {}
    }, 5000)
    return () => clearInterval(t)
  }, [docs, page])

  const totalPages = Math.ceil(total / 10)

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.title}>My Documents</h1>
          <p className={styles.sub}>{total} contract{total !== 1 ? 's' : ''} analyzed</p>
        </div>
        <button className={styles.uploadBtn} onClick={() => navigate('/upload')}>
          + Upload Contract
        </button>
      </div>

      {user && !user.is_verified && (
        <VerificationBanner email={user.email} />
      )}

      {loading ? (
        <SkeletonTable rows={5} />
      ) : docs.length === 0 ? (
        <div className={styles.empty}>
          <div className={styles.emptyIcon}>📄</div>
          <h3>No documents yet</h3>
          <p>Upload your first rental contract to get started.</p>
          <button className={styles.uploadBtn} onClick={() => navigate('/upload')}>
            Upload Contract
          </button>
        </div>
      ) : (
        <>
          <div className={styles.table}>
            <div className={styles.thead}>
              <div className={styles.tr}>
                <div className={styles.th} style={{ flex: 3 }}>Filename</div>
                <div className={styles.th} style={{ flex: 1 }}>Status</div>
                <div className={styles.th} style={{ flex: 1 }}>Risk</div>
                <div className={styles.th} style={{ flex: 1 }}>Date</div>
                <div className={styles.th} style={{ flex: 1 }}>Action</div>
              </div>
            </div>
            <div className={styles.tbody}>
              {docs.map(doc => (
                <div key={doc.id} className={styles.tr}>
                  <div className={styles.td} style={{ flex: 3 }}>
                    <span className={styles.filename}>{doc.original_filename}</span>
                    <span className={styles.filesize}>{(doc.file_size_bytes / 1024).toFixed(0)} KB</span>
                  </div>
                  <div className={styles.td} style={{ flex: 1 }}>
                    <StatusBadge status={doc.status} />
                  </div>
                  <div className={styles.td} style={{ flex: 1 }}>
                    {doc.analysis?.risk_score && (
                      <span className={styles.risk} style={{ color: RISK_META[doc.analysis.risk_score]?.color }}>
                        {RISK_META[doc.analysis.risk_score]?.label}
                      </span>
                    )}
                  </div>
                  <div className={styles.td} style={{ flex: 1 }}>
                    <span className={styles.date}>
                      {new Date(doc.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}
                    </span>
                  </div>
                  <div className={styles.td} style={{ flex: 1 }}>
                    {doc.status === 'completed' && (
                      <button className={styles.viewBtn} onClick={() => navigate(`/documents/${doc.id}`)}>
                        View
                      </button>
                    )}
                    {doc.status === 'failed' && (
                      <span className={styles.failedHint} title={doc.error_message}>Failed</span>
                    )}
                  </div>
                </div>
              ))}
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