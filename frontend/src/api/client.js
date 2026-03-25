import axios from 'axios'

// In dev: vite proxy handles /api → localhost:8000
// In prod: VITE_API_URL points directly to Railway backend
const baseURL = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL
  : '/api'

const api = axios.create({
  baseURL,
  timeout: 60000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

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

export const authApi = {
  register:           (data)    => api.post('/auth/register', data),
  login:              (data)    => api.post('/auth/login', data),
  me:                 ()        => api.get('/auth/me'),
  verifyEmail:        (token)   => api.get('/auth/verify-email', { params: { token } }),
  resendVerification: (email)   => api.post('/auth/resend-verification', { email }),
}

export const documentsApi = {
  upload: (formData) => api.post('/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  list:      (page = 1, pageSize = 20) => api.get('/documents', { params: { page, page_size: pageSize } }),
  get:       (id)  => api.get(`/documents/${id}`),
  delete:    (id)  => api.delete(`/documents/${id}`),
  reanalyze: (id)  => api.post(`/documents/${id}/reanalyze`),
  keep:      (id)  => api.post(`/documents/${id}/keep`),
}

export const adminApi = {
  stats:          ()         => api.get('/admin/stats'),
  users:          (page = 1) => api.get('/admin/users', { params: { page } }),
  getUser:        (id)       => api.get(`/admin/users/${id}`),
  deactivateUser: (id)       => api.patch(`/admin/users/${id}/deactivate`),
  activateUser:   (id)       => api.patch(`/admin/users/${id}/activate`),
  documents:      (page = 1, status = '') =>
    api.get('/admin/documents', { params: { page, ...(status && { status }) } }),
  getDocument:    (id)       => api.get(`/admin/documents/${id}`),
}

export default api