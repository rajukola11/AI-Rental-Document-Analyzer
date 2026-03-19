import { useState, useEffect } from 'react'
import { adminApi } from '../../api/client'
import styles from './AdminUsers.module.css'

export default function AdminUsers() {
  const [users, setUsers]   = useState([])
  const [loading, setLoading] = useState(true)
  const [actionId, setActionId] = useState(null)

  const load = () => {
    setLoading(true)
    adminApi.users()
      .then(r => setUsers(r.data))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const toggle = async (user) => {
    setActionId(user.id)
    try {
      if (user.is_active) {
        await adminApi.deactivateUser(user.id)
      } else {
        await adminApi.activateUser(user.id)
      }
      load()
    } catch (e) {
      console.error(e)
    } finally {
      setActionId(null)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.title}>Users</h1>
          <p className={styles.sub}>{users.length} registered accounts</p>
        </div>
      </div>

      {loading ? (
        <div className={styles.loading}>Loading users…</div>
      ) : (
        <div className={styles.table}>
          <div className={styles.thead}>
            <div className={styles.tr}>
              <div className={styles.th} style={{ flex: 2 }}>User</div>
              <div className={styles.th} style={{ flex: 1 }}>Role</div>
              <div className={styles.th} style={{ flex: 1 }}>Uploads</div>
              <div className={styles.th} style={{ flex: 1 }}>Status</div>
              <div className={styles.th} style={{ flex: 1 }}>Joined</div>
              <div className={styles.th} style={{ flex: 1 }}>Action</div>
            </div>
          </div>
          <div className={styles.tbody}>
            {users.map(u => (
              <div key={u.id} className={styles.tr}>
                <div className={styles.td} style={{ flex: 2 }}>
                  <div className={styles.userCell}>
                    <div className={styles.avatar}>
                      {(u.full_name || u.email)[0].toUpperCase()}
                    </div>
                    <div>
                      <div className={styles.userName}>{u.full_name || '—'}</div>
                      <div className={styles.userEmail}>{u.email}</div>
                    </div>
                  </div>
                </div>
                <div className={styles.td} style={{ flex: 1 }}>
                  <span className={`${styles.roleBadge} ${u.role === 'admin' ? styles.admin : styles.user}`}>
                    {u.role}
                  </span>
                </div>
                <div className={styles.td} style={{ flex: 1 }}>
                  <span className={styles.mono}>{u.uploads_used}</span>
                </div>
                <div className={styles.td} style={{ flex: 1 }}>
                  <span className={`${styles.statusDot} ${u.is_active ? styles.active : styles.inactive}`}>
                    {u.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>
                <div className={styles.td} style={{ flex: 1 }}>
                  <span className={styles.date}>
                    {new Date(u.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}
                  </span>
                </div>
                <div className={styles.td} style={{ flex: 1 }}>
                  {u.role !== 'admin' && (
                    <button
                      className={`${styles.toggleBtn} ${u.is_active ? styles.deactivate : styles.activate}`}
                      onClick={() => toggle(u)}
                      disabled={actionId === u.id}
                    >
                      {actionId === u.id ? '…' : u.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}