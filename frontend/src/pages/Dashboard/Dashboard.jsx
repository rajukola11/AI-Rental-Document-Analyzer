import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { documentsApi } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import { useToast } from '../../components/ui/Toast'
import { SkeletonTable } from '../../components/ui/Skeleton'
import VerificationBanner from '../../components/ui/VerificationBanner'
import styles from './Dashboard.module.css'

const STATUS_META = {
  uploaded:   { label: 'Queued',             color: 'var(--text-muted)',  bg: 'var(--surface-2)' },
  processing: { label: 'Analyzing',          color: 'var(--warning)',     bg: 'var(--warning-light)' },
  completed:  { label: 'Completed',          color: 'var(--success)',     bg: 'var(--success-light)' },
  failed:     { label: 'Failed',             color: 'var(--danger)',      bg: 'var(--danger-light)' },
  deleted:    { label: 'Deleted for privacy',color: 'var(--text-muted)',  bg: 'var(--surface-2)' },
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

function ExpiryBadge({ expiresAt, isDeleted }) {
  if (isDeleted || !expiresAt) return null
  const diff = new Date(expiresAt) - new Date()
  const hours = Math.floor(diff / 1000 / 60 / 60)
  if (hours > 48) return null  // don't show if more than 2 days left
  const label = hours <= 0 ? 'Expiring soon' : hours < 24 ? `${hours}h left` : `${Math.floor(hours/24)}d left`
  return <span className={styles.expiryWarn}>⏳ {label}</span>
}

export default function Dashboard() {
  const { user } = useAuth()
  const navigate  = useNavigate()
  const toast     = useToast()
  const [docs, setDocs]           = useState([])
  const [total, setTotal]         = useState(0)
  const [page, setPage]           = useState(1)
  const [loading, setLoading]     = useState(true)
  const [deleting, setDeleting]   = useState(null)
  const [reanalyzing, setReanalyzing] = useState(null)

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

  // Poll while any doc is processing
  useEffect(() => {
    const hasActive = docs.some(d => d.status === 'processing' || d.status === 'uploaded')
    if (!hasActive) return
    const t = setInterval(async () => {
      try {
        const r = await documentsApi.list(page, 10)
        const newDocs = r.data.items
        newDocs.filter(nd => nd.status === 'completed' && docs.find(od => od.id === nd.id)?.status !== 'completed')
          .forEach(d => toast.success(`Analysis complete: ${d.original_filename}`))
        setDocs(newDocs)
        setTotal(r.data.total)
      } catch {}
    }, 5000)
    return () => clearInterval(t)
  }, [docs, page])

  const handleDelete = async (doc) => {
    if (!window.confirm(`Delete "${doc.original_filename}"? This cannot be undone.`)) return
    setDeleting(doc.id)
    try {
      await documentsApi.delete(doc.id)
      toast.success('Document deleted.')
      setDocs(prev => prev.map(d => d.id === doc.id ? { ...d, status: 'deleted', is_deleted: true } : d))
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Delete failed.')
    } finally {
      setDeleting(null)
    }
  }

  const handleReanalyze = async (doc) => {
    setReanalyzing(doc.id)
    try {
      await documentsApi.reanalyze(doc.id)
      toast.success('Reanalysis started — this is free since the document failed.')
      setDocs(prev => prev.map(d => d.id === doc.id ? { ...d, status: 'processing' } : d))
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Reanalysis failed to start.')
    } finally {
      setReanalyzing(null)
    }
  }

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

      {user && !user.is_verified && <VerificationBanner email={user.email} />}

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
                <div className={styles.th} style={{ flex: 1.5 }}>Status</div>
                <div className={styles.th} style={{ flex: 1 }}>Risk</div>
                <div className={styles.th} style={{ flex: 1 }}>Date</div>
                <div className={styles.th} style={{ flex: 2 }}>Actions</div>
              </div>
            </div>
            <div className={styles.tbody}>
              {docs.map(doc => (
                <div key={doc.id} className={`${styles.tr} ${doc.is_deleted ? styles.deletedRow : ''}`}>
                  <div className={styles.td} style={{ flex: 3 }}>
                    <span className={styles.filename}>{doc.original_filename}</span>
                    <span className={styles.filesize}>{(doc.file_size_bytes / 1024).toFixed(0)} KB</span>
                    <ExpiryBadge expiresAt={doc.expires_at} isDeleted={doc.is_deleted} />
                  </div>
                  <div className={styles.td} style={{ flex: 1.5 }}>
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
                  <div className={styles.td} style={{ flex: 2, gap: '6px', display: 'flex', flexWrap: 'wrap' }}>
                    {doc.status === 'completed' && !doc.is_deleted && (
                      <button className={styles.viewBtn} onClick={() => navigate(`/app/documents/${doc.id}`)}>
                        View
                      </button>
                    )}
                    {doc.status === 'failed' && !doc.is_deleted && (
                      <button
                        className={styles.reanalyzeBtn}
                        onClick={() => handleReanalyze(doc)}
                        disabled={reanalyzing === doc.id}
                        title="Free retry — document failed to analyze"
                      >
                        {reanalyzing === doc.id ? '…' : '↺ Retry'}
                      </button>
                    )}
                    {!doc.is_deleted && (
                      <button
                        className={styles.deleteBtn}
                        onClick={() => handleDelete(doc)}
                        disabled={deleting === doc.id}
                        title="Delete document"
                      >
                        {deleting === doc.id ? '…' : '🗑'}
                      </button>
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