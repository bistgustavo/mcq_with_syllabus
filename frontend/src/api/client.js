// Thin fetch wrapper: attaches the bearer token, parses JSON, normalises errors.

const BASE = import.meta.env.VITE_API_BASE_URL || ''
const TOKEN_KEY = 'mcq_token'

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage unavailable: session-only login */
  }
}

export class ApiError extends Error {
  constructor(status, message, body) {
    super(message)
    this.status = status
    this.body = body
  }
}

let onUnauthorized = () => {}
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

function errorMessage(body, status) {
  if (!body) return `Request failed (${status})`
  const { detail } = body
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d) => `${(d.loc || []).filter((p) => p !== 'body').join('.')}: ${d.msg}`)
      .join('; ')
  }
  return `Request failed (${status})`
}

export async function request(path, { method = 'GET', body, form, files, signal } = {}) {
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  let payload
  if (files) {
    payload = new FormData()
    Object.entries(files).forEach(([k, v]) => payload.append(k, v))
  } else if (form) {
    payload = new URLSearchParams(form)
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
  } else if (body !== undefined) {
    payload = JSON.stringify(body)
    headers['Content-Type'] = 'application/json'
  }

  let res
  try {
    res = await fetch(`${BASE}/api/v1${path}`, { method, headers, body: payload, signal })
  } catch (err) {
    if (err.name === 'AbortError') throw err
    throw new ApiError(0, 'Cannot reach the server. Is the backend running?')
  }

  if (res.status === 204) return null
  const text = await res.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = { detail: text }
  }

  if (!res.ok) {
    if (res.status === 401 && token) onUnauthorized()
    throw new ApiError(res.status, errorMessage(data, res.status), data)
  }
  return data
}

const qs = (params) => {
  const s = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  ).toString()
  return s ? `?${s}` : ''
}

export const api = {
  // auth
  register: (data) => request('/auth/register', { method: 'POST', body: data }),
  login: (email, password) => request('/auth/login', { method: 'POST', form: { username: email, password } }),
  me: () => request('/auth/me'),
  updateMe: (data) => request('/auth/me', { method: 'PATCH', body: data }),

  // courses / chapters / topics
  courses: () => request('/courses'),
  course: (id) => request(`/courses/${id}`),
  createCourse: (data) => request('/courses', { method: 'POST', body: data }),
  updateCourse: (id, data) => request(`/courses/${id}`, { method: 'PATCH', body: data }),
  deleteCourse: (id) => request(`/courses/${id}`, { method: 'DELETE' }),
  createChapter: (data) => request('/chapters', { method: 'POST', body: data }),
  updateChapter: (id, data) => request(`/chapters/${id}`, { method: 'PATCH', body: data }),
  deleteChapter: (id) => request(`/chapters/${id}`, { method: 'DELETE' }),
  createTopic: (data) => request('/topics', { method: 'POST', body: data }),
  updateTopic: (id, data) => request(`/topics/${id}`, { method: 'PATCH', body: data }),
  deleteTopic: (id) => request(`/topics/${id}`, { method: 'DELETE' }),
  topic: (id) => request(`/topics/${id}`),
  topicStatus: (id) => request(`/topics/${id}/status`),
  topicStats: (id) => request(`/topics/${id}/stats`),

  // documents
  upload: (topicId, file) => request(`/topics/${topicId}/upload-syllabus`, { method: 'POST', files: { file } }),
  reingest: (topicId, docId) => request(`/topics/${topicId}/documents/${docId}/reingest`, { method: 'POST' }),
  deleteDocument: (topicId, docId) => request(`/topics/${topicId}/documents/${docId}`, { method: 'DELETE' }),

  // generation & question bank
  generate: (topicId, data) => request(`/topics/${topicId}/generate-questions`, { method: 'POST', body: data }),
  task: (taskId) => request(`/tasks/${taskId}`),
  questions: (topicId, params = {}) => request(`/topics/${topicId}/questions${qs(params)}`),
  deleteQuestion: (topicId, qid) => request(`/topics/${topicId}/questions/${qid}`, { method: 'DELETE' }),

  // quiz
  startQuiz: (topicId, params) => request(`/topics/${topicId}/quiz${qs(params)}`),
  submitQuiz: (data) => request('/quiz-attempts', { method: 'POST', body: data }),
  attempts: (params = {}) => request(`/quiz-attempts/me${qs(params)}`),
  attempt: (id) => request(`/quiz-attempts/${id}`),
  dashboard: () => request('/me/dashboard'),

  // admin
  overview: () => request('/admin/overview'),
  users: () => request('/admin/users'),
  updateUser: (id, data) => request(`/admin/users/${id}`, { method: 'PATCH', body: data }),
  health: () => request('/health/deep'),

  // syllabus & exam pattern
  syllabus: (courseId) => request(`/courses/${courseId}/syllabus`),
  importSyllabus: (courseId, text, mode = 'merge') =>
    request(`/courses/${courseId}/syllabus`, { method: 'POST', body: { text, mode } }),
  readiness: (courseId, paper) => request(`/courses/${courseId}/readiness${qs({ paper })}`),

  // content pipeline
  research: (topicId) => request(`/topics/${topicId}/research`, { method: 'POST' }),
  buildBank: (courseId, data) => request(`/courses/${courseId}/build-bank`, { method: 'POST', body: data }),
  bankJob: (courseId) => request(`/courses/${courseId}/build-bank`),
  questionSources: (courseId) => request(`/courses/${courseId}/question-sources`),
  uploadPastPaper: (courseId, file, label, paper) =>
    request(`/courses/${courseId}/past-papers`, { method: 'POST', files: { file, label, ...(paper ? { paper } : {}) } }),
  collectOnline: (courseId) => request(`/courses/${courseId}/collect-online`, { method: 'POST' }),
  pastPapers: (courseId) => request(`/courses/${courseId}/past-papers`),
  findPastPapers: (courseId) => request(`/courses/${courseId}/past-papers/find`, { method: 'POST' }),
  reprocessPaper: (id) => request(`/past-papers/${id}/process`, { method: 'POST' }),
  deletePaper: (id) => request(`/past-papers/${id}`, { method: 'DELETE' }),
  paperFileUrl: (id) => `${BASE}/api/v1/past-papers/${id}/file`,

  // mock exams
  startExam: (courseId, paper) => request(`/courses/${courseId}/mock-exams`, { method: 'POST', body: { paper: paper || null } }),
  exam: (id) => request(`/mock-exams/${id}`),
  saveExam: (id, data) => request(`/mock-exams/${id}/progress`, { method: 'PUT', body: data }),
  submitExam: (id, data) => request(`/mock-exams/${id}/submit`, { method: 'POST', body: data }),
  myExams: () => request('/mock-exams/me'),

  // branding / public
  branding: () => request('/settings/branding'),
  updateBranding: (data) => request('/settings/branding', { method: 'PUT', body: data }),
  publicStats: () => request('/settings/public-stats'),
}
