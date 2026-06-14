'use client'

import { useState } from 'react'
import AppShell from '@/components/AppShell'

const MEMBERS = [
  { name: 'Tejas C.',      email: 'tejas@company.com', role: 'Super Admin', status: 'active', lastActive: 'Now' },
  { name: 'Sarah M.',      email: 'sarah.m@company.com', role: 'Data Scientist', status: 'active', lastActive: '2h ago' },
  { name: 'Rahul K.',      email: 'rahul.k@company.com', role: 'Data Scientist', status: 'active', lastActive: '5h ago' },
  { name: 'Jennifer T.',   email: 'jennifer.t@company.com', role: 'View Only (C-Suite)', status: 'active', lastActive: '1d ago' },
  { name: 'Marcus L.',     email: 'marcus.l@company.com', role: 'View Only (C-Suite)', status: 'inactive', lastActive: '7d ago' },
]

const AUDIT = [
  { time: '09:05:12', user: 'Tejas C.', action: 'Triggered Force Retrain', target: 'Employee Attrition v1.0', status: 'success' },
  { time: '09:00:01', user: 'System',   action: 'Auto-drift check completed', target: 'All Models', status: 'info' },
  { time: '08:45:33', user: 'Sarah M.', action: 'Updated drift threshold', target: 'Pipelines Config', status: 'success' },
  { time: '08:30:00', user: 'System',   action: 'Window2 data ingested', target: 'Data Pipeline', status: 'info' },
  { time: 'Yesterday', user: 'Marcus L.', action: 'Viewed dashboard', target: 'Global Dashboard', status: 'neutral' },
]

const ROLE_COLOR = { 'Super Admin': '#FAFAFA', 'Data Scientist': '#A3A3A3', 'View Only (C-Suite)': '#525252' }
const AUDIT_COLOR = { success: '#22C55E', info: '#A3A3A3', neutral: '#525252' }

export default function TeamPage() {
  const [inviteEmail, setInviteEmail] = useState('')

  return (
    <AppShell title="Team & IAM">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', borderBottom: '1px solid #262626', paddingBottom: '16px', marginBottom: '32px' }}>
        <div>
          <h1 style={{ fontSize: '28px', fontWeight: 600, letterSpacing: '-0.02em' }}>Team & Governance</h1>
          <p style={{ color: '#A3A3A3', marginTop: '4px', fontSize: '13px' }}>Identity access management, roles, and full audit trail.</p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <input
            type="email"
            placeholder="email@company.com"
            value={inviteEmail}
            onChange={e => setInviteEmail(e.target.value)}
            style={{
              background: '#141414', border: '1px solid #262626', color: '#FAFAFA',
              padding: '8px 16px', fontFamily: 'Geist Mono', fontSize: '12px',
              outline: 'none', width: '220px',
            }}
          />
          <button className="btn-primary">Invite Member</button>
        </div>
      </div>

      {/* Roles reference */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1px', background: '#262626', marginBottom: '32px' }}>
        {[
          { role: 'Super Admin',           perms: 'Full access — can retrain, configure, invite, view all data.', color: '#FAFAFA' },
          { role: 'Data Scientist',        perms: 'Can trigger adaptations, configure thresholds, view all.', color: '#A3A3A3' },
          { role: 'View Only (C-Suite)',   perms: 'Read-only access to dashboards and executive summaries.', color: '#525252' },
        ].map(r => (
          <div key={r.role} className="card" style={{ background: '#141414', padding: '20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <div style={{ width: '8px', height: '8px', background: r.color }} />
              <span className="mono" style={{ fontSize: '11px', color: r.color, letterSpacing: '0.06em' }}>{r.role.toUpperCase()}</span>
            </div>
            <p style={{ fontSize: '12px', color: '#525252', lineHeight: '1.6' }}>{r.perms}</p>
          </div>
        ))}
      </div>

      {/* Members table */}
      <div style={{ borderBottom: '1px solid #262626', paddingBottom: '12px', marginBottom: '16px' }}>
        <div className="label">Team Members</div>
      </div>
      <div className="card" style={{ background: '#141414', marginBottom: '32px' }}>
        <table>
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Last Active</th><th>Actions</th></tr></thead>
          <tbody>
            {MEMBERS.map(m => (
              <tr key={m.email}>
                <td style={{ fontWeight: 500 }}>{m.name}</td>
                <td style={{ color: '#A3A3A3' }}>{m.email}</td>
                <td>
                  <span className="mono" style={{ fontSize: '11px', color: ROLE_COLOR[m.role as keyof typeof ROLE_COLOR] }}>
                    {m.role}
                  </span>
                </td>
                <td>
                  <span className="chip" style={{ borderLeftColor: m.status === 'active' ? '#22C55E' : '#525252', color: m.status === 'active' ? '#22C55E' : '#525252' }}>
                    {m.status.toUpperCase()}
                  </span>
                </td>
                <td className="mono" style={{ fontSize: '11px', color: '#525252' }}>{m.lastActive}</td>
                <td>
                  <button className="btn-secondary" style={{ fontSize: '10px', padding: '4px 10px', color: '#525252' }}>Edit</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Audit log */}
      <div style={{ borderBottom: '1px solid #262626', paddingBottom: '12px', marginBottom: '16px' }}>
        <div className="label">Audit Log</div>
      </div>
      <div className="card" style={{ background: '#141414' }}>
        <table>
          <thead><tr><th>Timestamp</th><th>User</th><th>Action</th><th>Target</th><th>Status</th></tr></thead>
          <tbody>
            {AUDIT.map((a, i) => (
              <tr key={i}>
                <td className="mono" style={{ fontSize: '11px', color: '#525252' }}>{a.time}</td>
                <td style={{ color: '#FAFAFA' }}>{a.user}</td>
                <td style={{ color: '#A3A3A3' }}>{a.action}</td>
                <td className="mono" style={{ fontSize: '11px', color: '#525252' }}>{a.target}</td>
                <td>
                  <div style={{ width: '8px', height: '8px', background: AUDIT_COLOR[a.status as keyof typeof AUDIT_COLOR] }} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AppShell>
  )
}
