export const DEFAULT_API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  (typeof window !== 'undefined'
    ? `${window.location.protocol}//${window.location.hostname}:8002`
    : 'http://localhost:8002')

export const API_BASE = DEFAULT_API_URL.replace(/\/$/, '')

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const hasBody = options?.body !== undefined
  const headers = new Headers(options?.headers)
  if (hasBody && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!response.ok) throw new Error(`API error ${response.status}: ${path}`)
  return response.json() as Promise<T>
}

export const WS_URL = DEFAULT_API_URL.replace(/^http/, 'ws') + '/ws/now_playing'
