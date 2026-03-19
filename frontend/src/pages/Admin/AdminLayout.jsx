import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import styles from './AdminLayout.module.css'

const NAV = [
  { to: '/admin',           icon: '▦', label: 'Overview',  end: true },
  { to: '/admin/users',     icon: '👥', label: 'Users' },
  { to: '/admin/documents', icon: '📄', label: 'Documents' },
]

export default function AdminLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.logo}>
          <span className={styles.logoMark}>RA</span>
          <div>
            <span className={styles.logoText}>RentalAI</span>
            <span className={styles.adminBadge}>Admin</span>
          </div>
        </div>

        <nav className={styles.nav}>
          {NAV.map(n => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                `${styles.navItem} ${isActive ? styles.active : ''}`
              }
            >
              <span className={styles.navIcon}>{n.icon}</span>
              <span>{n.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className={styles.sidebarFooter}>
          <button className={styles.switchBtn} onClick={() => navigate('/dashboard')}>
            ← User view
          </button>
          <div className={styles.userRow}>
            <div className={styles.avatar}>
              {(user?.full_name || user?.email || 'A')[0].toUpperCase()}
            </div>
            <div className={styles.userInfo}>
              <span className={styles.userName}>{user?.full_name || 'Admin'}</span>
              <span className={styles.userEmail}>{user?.email}</span>
            </div>
          </div>
          <button className={styles.logoutBtn} onClick={logout}>Sign out</button>
        </div>
      </aside>

      <div className={styles.main}>
        <header className={styles.header}>
          <h2 className={styles.headerTitle}>Admin Panel</h2>
          <span className={styles.headerBadge}>Admin Access</span>
        </header>
        <main className={styles.content}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}