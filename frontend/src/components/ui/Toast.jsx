import { useState, useCallback, createContext, useContext } from 'react'
import styles from './Toast.module.css'

const ToastContext = createContext(null)

let _id = 0

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const add = useCallback((message, type = 'info', duration = 4000) => {
    const id = ++_id
    setToasts(t => [...t, { id, message, type }])
    setTimeout(() => remove(id), duration)
  }, [])

  const remove = useCallback((id) => {
    setToasts(t => t.filter(x => x.id !== id))
  }, [])

  const toast = {
    success: (msg, dur)  => add(msg, 'success', dur),
    error:   (msg, dur)  => add(msg, 'error',   dur || 6000),
    info:    (msg, dur)  => add(msg, 'info',     dur),
    warning: (msg, dur)  => add(msg, 'warning',  dur),
  }

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div className={styles.container}>
        {toasts.map(t => (
          <div key={t.id} className={`${styles.toast} ${styles[t.type]}`}>
            <span className={styles.icon}>
              {t.type === 'success' && '✓'}
              {t.type === 'error'   && '✕'}
              {t.type === 'warning' && '⚠'}
              {t.type === 'info'    && 'ℹ'}
            </span>
            <span className={styles.message}>{t.message}</span>
            <button className={styles.close} onClick={() => remove(t.id)}>✕</button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export const useToast = () => useContext(ToastContext)