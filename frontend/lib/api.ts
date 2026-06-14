'use client'

import { useEffect, useState } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export type BackendStatus = 'checking' | 'online' | 'offline'

export function useBackendStatus() {
  const [status, setStatus] = useState<BackendStatus>('checking')

  useEffect(() => {
    fetch(`${API}/`)
      .then(r => r.ok ? setStatus('online') : setStatus('offline'))
      .catch(() => setStatus('offline'))
  }, [])

  return status
}

export function apiFetch(path: string, options?: RequestInit) {
  return fetch(`${API}${path}`, options).then(res => {
    if (!res.ok) throw new Error(`API error: ${res.status}`)
    return res.json()
  })
}
