import { useState } from 'react'
import { authApi } from '../../api/client'
import styles from './VerificationBanner.module.css'

export default function VerificationBanner({ email }) {
  const [status, setStatus] = useState('idle') // idle | sending | sent | error

  const resend = async () => {
    setStatus('sending')
    try {
      await authApi.resendVerification(email)
      setStatus('sent')
    } catch {
      setStatus('error')
    }
  }

  return (
    <div className={styles.banner}>
      <span className={styles.icon}>✉️</span>
      <div className={styles.text}>
        <strong>Verify your email to start analyzing contracts.</strong>
        {' '}We sent a link to <strong>{email}</strong>. Check your inbox (and spam folder).
      </div>
      <div className={styles.actions}>
        {status === 'idle' && (
          <button className={styles.resendBtn} onClick={resend}>
            Resend link
          </button>
        )}
        {status === 'sending' && (
          <span className={styles.sending}>Sending…</span>
        )}
        {status === 'sent' && (
          <span className={styles.sent}>✓ Sent! Check your inbox.</span>
        )}
        {status === 'error' && (
          <button className={styles.resendBtn} onClick={resend}>
            Failed — try again
          </button>
        )}
      </div>
    </div>
  )
}