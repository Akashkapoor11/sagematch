const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export async function getJSON(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options)
  let payload = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }
  if (!response.ok) {
    throw new Error(payload?.detail || `Request failed (${response.status})`)
  }
  return payload
}

export function uploadCatalogue(file) {
  const form = new FormData()
  form.append('file', file)
  return getJSON('/api/catalog/upload', { method: 'POST', body: form })
}
