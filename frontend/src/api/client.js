import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

// Attach JWT to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Auto-logout on 401
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authApi = {
  register: (data) => api.post('/auth/register', data),
  login:    (data) => api.post('/auth/login', data),
  me:       ()     => api.get('/auth/me'),
}

// ── Documents ─────────────────────────────────────────────────────────────────
export const documentsApi = {
  upload: (formData) =>
    api.post('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  list:   (page = 1, pageSize = 20) =>
    api.get('/documents', { params: { page, page_size: pageSize } }),
  get:    (id) => api.get(`/documents/${id}`),
}

// ── Admin ─────────────────────────────────────────────────────────────────────
export const adminApi = {
  stats:          ()        => api.get('/admin/stats'),
  users:          (page=1)  => api.get('/admin/users', { params: { page } }),
  getUser:        (id)      => api.get(`/admin/users/${id}`),
  deactivateUser: (id)      => api.patch(`/admin/users/${id}/deactivate`),
  activateUser:   (id)      => api.patch(`/admin/users/${id}/activate`),
  documents:      (page=1, status='') =>
    api.get('/admin/documents', { params: { page, ...(status && { status }) } }),
  getDocument:    (id)      => api.get(`/admin/documents/${id}`),
}

export default api