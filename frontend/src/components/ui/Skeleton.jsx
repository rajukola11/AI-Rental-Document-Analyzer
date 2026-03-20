import styles from './Skeleton.module.css'

export function Skeleton({ width = '100%', height = '16px', radius = '4px', className = '' }) {
  return (
    <div
      className={`${styles.skeleton} ${className}`}
      style={{ width, height, borderRadius: radius }}
    />
  )
}

export function SkeletonText({ lines = 3, lastWidth = '60%' }) {
  return (
    <div className={styles.textBlock}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          width={i === lines - 1 ? lastWidth : '100%'}
          height="14px"
        />
      ))}
    </div>
  )
}

export function SkeletonCard() {
  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <Skeleton width="120px" height="12px" />
        <Skeleton width="60px" height="20px" radius="20px" />
      </div>
      <SkeletonText lines={2} lastWidth="40%" />
    </div>
  )
}

export function SkeletonTable({ rows = 5 }) {
  return (
    <div className={styles.table}>
      <div className={styles.tableHeader}>
        {[3, 1, 1, 1, 1].map((flex, i) => (
          <Skeleton key={i} width={`${flex * 15}%`} height="11px" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className={styles.tableRow}>
          <Skeleton width="35%" height="13px" />
          <Skeleton width="10%" height="20px" radius="20px" />
          <Skeleton width="10%" height="13px" />
          <Skeleton width="12%" height="13px" />
          <Skeleton width="8%"  height="26px" radius="6px" />
        </div>
      ))}
    </div>
  )
}