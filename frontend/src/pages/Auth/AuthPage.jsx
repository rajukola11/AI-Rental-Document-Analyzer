import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import styles from './AuthPage.module.css'

export default function AuthPage({ mode }) {
  const { login, register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm]     = useState({ email: '', password: '', full_name: '' })
  const [error, setError]   = useState('')
  const [loading, setLoading] = useState(false)

  const isLogin = mode === 'login'

  const handle = (e) => setForm(f => ({ ...f, [e.target.name]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (isLogin) {
        await login(form.email, form.password)
      } else {
        await register(form.email, form.password, form.full_name)
      }
      navigate('/dashboard')
    } catch (err) {
      setError(err.response?.data?.detail || 'Something went wrong.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.left}>
        <div className={styles.brand}>
          <span className={styles.logoMark}>RA</span>
          <span className={styles.logoText}>RentalAI</span>
        </div>
        <div className={styles.hero}>
          <h1 className={styles.heroTitle}>Understand your rental contract in minutes</h1>
          <p className={styles.heroSub}>AI-powered analysis of German rental contracts. Get plain-English summaries, risk flags, and clause explanations.</p>
          <div className={styles.features}>
            {['Instant clause extraction', 'Risk detection & scoring', 'Plain-English explanations', 'Secure document storage'].map(f => (
              <div key={f} className={styles.feature}>
                <span className={styles.featureCheck}>✓</span>
                <span>{f}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className={styles.right}>
        <div className={styles.card}>
          <h2 className={styles.title}>{isLogin ? 'Welcome back' : 'Create account'}</h2>
          <p className={styles.subtitle}>
            {isLogin ? 'Sign in to your account' : 'Start analyzing rental contracts'}
          </p>

          <form className={styles.form} onSubmit={submit}>
            {!isLogin && (
              <div className={styles.field}>
                <label className={styles.label}>Full name</label>
                <input
                  className={styles.input}
                  name="full_name"
                  placeholder="Your name"
                  value={form.full_name}
                  onChange={handle}
                />
              </div>
            )}
            <div className={styles.field}>
              <label className={styles.label}>Email address</label>
              <input
                className={styles.input}
                name="email"
                type="email"
                placeholder="you@example.com"
                value={form.email}
                onChange={handle}
                required
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>Password</label>
              <input
                className={styles.input}
                name="password"
                type="password"
                placeholder={isLogin ? '••••••••' : 'Min. 8 characters'}
                value={form.password}
                onChange={handle}
                required
              />
            </div>

            {error && <div className={styles.error}>{error}</div>}

            <button className={styles.btn} type="submit" disabled={loading}>
              {loading ? 'Please wait…' : isLogin ? 'Sign in' : 'Create account'}
            </button>
          </form>

          <p className={styles.switch}>
            {isLogin ? "Don't have an account? " : 'Already have an account? '}
            <Link to={isLogin ? '/register' : '/login'} className={styles.switchLink}>
              {isLogin ? 'Register' : 'Sign in'}
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}