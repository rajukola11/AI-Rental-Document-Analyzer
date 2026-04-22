import { Component } from 'react'
import styles from './ErrorBoundary.module.css'

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, info) {
    console.error('ErrorBoundary caught:', error, info)
  }

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <div className={styles.icon}>⚠</div>
          <h2 className={styles.title}>Something went wrong</h2>
          <p className={styles.message}>
            {this.state.error?.message || 'An unexpected error occurred.'}
          </p>
          <div className={styles.actions}>
            <button
              className={styles.primaryBtn}
              onClick={() => this.setState({ hasError: false, error: null })}
            >
              Try again
            </button>
            <button
              className={styles.secondaryBtn}
              onClick={() => window.location.href = '/dashboard'}
            >
              Go to dashboard
            </button>
          </div>
        </div>
      </div>
    )
  }
}

export default ErrorBoundary