import axios from 'axios'
export const backendUnavailable = import.meta.env.VITE_HOSTED_FRONTEND === 'true' && !import.meta.env.VITE_API_BASE_URL
export const api = axios.create({baseURL: import.meta.env.VITE_API_BASE_URL || '/api', withCredentials: true})
export function errorText(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    return Array.isArray(detail) ? detail.map(d => d.msg).join('; ') : detail || 'Unable to connect. Check that the backend is running.'
  }
  return error instanceof Error ? error.message : 'An unexpected error occurred'
}
export function money(value: number | null | undefined) { return value == null ? 'Unavailable' : new Intl.NumberFormat('en-IN', {style:'currency',currency:'INR',maximumFractionDigits:0}).format(value) }
export function exportJSON(value: unknown, filename: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value,null,2)], {type:'application/json'}))
  const link = document.createElement('a'); link.href=url; link.download=filename; link.click(); URL.revokeObjectURL(url)
}
