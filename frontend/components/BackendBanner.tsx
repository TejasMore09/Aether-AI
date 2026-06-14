'use client'

import { useBackendStatus } from '@/lib/api'

export default function BackendBanner() {
  const status = useBackendStatus()

  if (status === 'checking' || status === 'online') return null

  return (
    <div style={{
      position: 'fixed', top: '56px', left: '256px', right: 0, zIndex: 100,
      background: '#1a0a0a', borderBottom: '1px solid #EF4444',
      padding: '10px 48px',
      display: 'flex', alignItems: 'center', gap: '12px',
    }}>
      <div style={{ width: '6px', height: '6px', background: '#EF4444' }} />
      <span className="mono" style={{ fontSize: '11px', color: '#EF4444', letterSpacing: '0.06em' }}>
        BACKEND OFFLINE
      </span>
      <span style={{ color: '#525252', fontSize: '12px' }}>
        FastAPI server is not reachable at <span className="mono" style={{ color: '#A3A3A3' }}>
          {process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}
        </span>.
        Run: <span className="mono" style={{ color: '#FAFAFA' }}>
          .\\venv\\Scripts\\uvicorn main:app --reload --port 8000
        </span>
      </span>
    </div>
  )
}
