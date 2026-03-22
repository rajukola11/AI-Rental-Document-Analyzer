import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate, Link } from 'react-router-dom'
import { authApi } from '../../api/client'
import styles from './VerifyEmail.module.css'

export default function VerifyEmail() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token')

  const [status, setStatus] = useState('verifying') // verifying | success | error | no-token
  const [errorMsg, setErrorMsg] = useState('')

  useEffect(() => {
    if (!token) {
      setStatus('no-token')
      return
    }

    authApi.verifyEmail(token)
      .then(() => {
        setStatus('success')
        // Update the stored user so the banner disappears without a full reload
        const stored = localStorage.getItem('user')
        if (stored) {
          try {
            const u = JSON.parse(stored)
            localStorage.setItem('user', JSON.stringify({ ...u, is_verified: true }))
          } catch {}
        }
        // Redirect to dashboard after 3s
        setTimeout(() => navigate('/dashboard'), 3000)
      })
      .catch((err) => {
        const msg = err.response?.data?.detail || 'Verification failed. The link may be invalid or expired.'
        setErrorMsg(msg)
        setStatus('error')
      })
  }, [token])

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.logo}>📄</div>

        {status === 'verifying' && (
          <>
            <div className={styles.spinner} />
            <h2 className={styles.title}>Verifying your email…</h2>
            <p className={styles.sub}>Just a moment.</p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className={styles.iconSuccess}>✓</div>
            <h2 className={styles.title}>Email verified!</h2>
            <p className={styles.sub}>
              Your account is active. You have 2 free analyses to get started.
            </p>
            <p className={styles.redirect}>Redirecting to your dashboard…</p>
            <Link to="/dashboard" className={styles.btn}>Go to dashboard now</Link>
          </>
        )}

        {status === 'error' && (
          <>
            <div className={styles.iconError}>✕</div>
            <h2 className={styles.title}>Verification failed</h2>
            <p className={styles.errorMsg}>{errorMsg}</p>
            <p className={styles.sub}>
              Request a new link from your dashboard or login page.
            </p>
            <Link to="/login" className={styles.btn}>Back to login</Link>
          </>
        )}

        {status === 'no-token' && (
          <>
            <div className={styles.iconError}>?</div>
            <h2 className={styles.title}>Invalid link</h2>
            <p className={styles.sub}>
              This verification link is missing a token. Check your email for the
              correct link, or request a new one.
            </p>
            <Link to="/login" className={styles.btn}>Back to login</Link>
          </>
        )}
      </div>
    </div>
  )
}