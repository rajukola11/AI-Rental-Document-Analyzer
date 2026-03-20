import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { documentsApi } from '../../api/client'
import { useToast } from '../../components/ui/Toast'
import styles from './Upload.module.css'

export default function Upload() {
  const navigate = useNavigate()
  const toast    = useToast()
  const inputRef = useRef()
  const [file, setFile]     = useState(null)
  const [drag, setDrag]     = useState(false)
  const [status, setStatus] = useState('idle')
  const [result, setResult] = useState(null)
  const [error, setError]   = useState('')

  const accept = (f) => {
    if (!f) return
    const ext = f.name.split('.').pop().toLowerCase()
    if (!['pdf', 'docx'].includes(ext)) {
      setError('Only PDF and DOCX files are supported.')
      toast.error('Only PDF and DOCX files are supported.')
      return
    }
    if (f.size > 20 * 1024 * 1024) {
      setError('File must be under 20 MB.')
      toast.error('File too large. Maximum size is 20 MB.')
      return
    }
    setFile(f)
    setError('')
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDrag(false)
    accept(e.dataTransfer.files[0])
  }

  const upload = async () => {
    if (!file) return
    setStatus('uploading')
    setError('')
    try {
      const fd = new FormData()
      fd.append('file', file)
      const r = await documentsApi.upload(fd)
      setResult(r.data)
      setStatus('success')
      toast.success('Document uploaded! Analysis is starting…')
    } catch (err) {
      const msg = err.response?.data?.detail || 'Upload failed. Please try again.'
      setError(msg)
      setStatus('error')
      toast.error(msg)
    }
  }

  const reset = () => { setFile(null); setStatus('idle'); setResult(null); setError('') }

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1 className={styles.title}>Upload Contract</h1>
        <p className={styles.sub}>Upload a German rental contract (PDF or DOCX) for AI analysis.</p>
      </div>

      <div className={styles.layout}>
        <div className={styles.uploadCard}>
          {status === 'success' ? (
            <div className={styles.success}>
              <div className={styles.successIcon}>✓</div>
              <h3>Upload successful</h3>
              <p>Your document is being analyzed. This takes 10–30 seconds.</p>
              <p className={styles.docId}>Document ID: <code>{result.id}</code></p>
              <div className={styles.successActions}>
                <button className={styles.primaryBtn} onClick={() => navigate('/dashboard')}>
                  View Dashboard
                </button>
                <button className={styles.secondaryBtn} onClick={reset}>
                  Upload Another
                </button>
              </div>
            </div>
          ) : (
            <>
              <div
                className={`${styles.dropzone} ${drag ? styles.dragOver : ''} ${file ? styles.hasFile : ''}`}
                onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
                onDragLeave={() => setDrag(false)}
                onDrop={onDrop}
                onClick={() => !file && inputRef.current.click()}
              >
                <input ref={inputRef} type="file" accept=".pdf,.docx" className={styles.hidden} onChange={(e) => accept(e.target.files[0])} />
                {file ? (
                  <div className={styles.filePreview}>
                    <div className={styles.fileIcon}>{file.name.endsWith('.pdf') ? '📄' : '📝'}</div>
                    <div className={styles.fileInfo}>
                      <span className={styles.fileName}>{file.name}</span>
                      <span className={styles.fileSize}>{(file.size / 1024).toFixed(0)} KB</span>
                    </div>
                    <button className={styles.removeBtn} onClick={(e) => { e.stopPropagation(); reset() }}>✕</button>
                  </div>
                ) : (
                  <div className={styles.dropContent}>
                    <div className={styles.dropIcon}>↑</div>
                    <p className={styles.dropText}>Drag & drop your contract here</p>
                    <p className={styles.dropSub}>or <span className={styles.browse}>browse files</span></p>
                    <p className={styles.dropHint}>PDF or DOCX · Max 20 MB</p>
                  </div>
                )}
              </div>
              {error && <div className={styles.errorMsg}>{error}</div>}
              <button className={styles.primaryBtn} onClick={upload} disabled={!file || status === 'uploading'}>
                {status === 'uploading' ? <><span className={styles.spinner} />Uploading…</> : 'Analyze Contract'}
              </button>
            </>
          )}
        </div>

        <div className={styles.infoPanel}>
          <h3 className={styles.infoTitle}>What we analyze</h3>
          {[
            { icon: '📋', title: 'Contract Summary', desc: 'Quick overview of key terms and parties involved.' },
            { icon: '🔍', title: 'Clause Extraction', desc: 'Rent, deposit, notice period, pets, subletting, and more.' },
            { icon: '⚠️', title: 'Risk Detection', desc: 'Flags unusual or tenant-unfavourable conditions.' },
            { icon: '🌐', title: 'Plain English', desc: 'Everything explained simply, even from German.' },
          ].map(item => (
            <div key={item.title} className={styles.infoItem}>
              <span className={styles.infoItemIcon}>{item.icon}</span>
              <div>
                <div className={styles.infoItemTitle}>{item.title}</div>
                <div className={styles.infoItemDesc}>{item.desc}</div>
              </div>
            </div>
          ))}
          <div className={styles.gdprNote}>
            <span className={styles.gdprIcon}>🔒</span>
            <p>Documents are processed securely and stored in your private account only.</p>
          </div>
        </div>
      </div>
    </div>
  )
}