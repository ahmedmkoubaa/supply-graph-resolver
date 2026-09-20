const API_BASE = import.meta.env.VITE_API_URL || '/api'

export async function api(path, params = {}) {
  const url = new URL(`${API_BASE}${path}`, window.location.origin)
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '' && value !== undefined && value !== null) url.searchParams.set(key, value)
  })
  const response = await fetch(url)
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `Request failed (${response.status})`)
  }
  return response.json()
}
