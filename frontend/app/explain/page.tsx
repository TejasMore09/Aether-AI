'use client'

import { useEffect, useRef, useState } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const DOMAINS = [
  { id: 'hr_attrition', name: 'HR Attrition' },
  { id: 'fin_fraud', name: 'Financial Fraud' },
  { id: 'crm_churn', name: 'CRM Churn' },
  { id: 'sec_threats', name: 'Security Threats' },
  { id: 'market_leads', name: 'Market Leads' },
  { id: 'supply_chain', name: 'Supply Chain' },
]

const SUGGESTED_QUESTIONS = [
  "Why did the model degrade?",
  "Should I retrain now?",
  "What is the current risk level?",
  "Which features are drifting?",
  "What is the expected financial impact?",
  "Is the model reliable for production?",
]

interface Message { role: 'user' | 'assistant'; content: string; ts: string }

export default function ExplainPage() {
  const [domain, setDomain] = useState('hr_attrition')
  const [role, setRole] = useState('executive')
  const [explanation, setExplanation] = useState('')
  const [summary, setSummary] = useState('')
  const [expLoading, setExpLoading] = useState(false)
  const [sumLoading, setSumLoading] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const chatRef = useRef<HTMLDivElement>(null)

  const fetchExplanation = () => {
    setExpLoading(true)
    fetch(`${API}/explain?domain=${domain}&role=${role}`)
      .then(r => r.json())
      .then(data => setExplanation(data.explanation || 'No explanation returned.'))
      .catch(() => setExplanation('Error fetching explanation.'))
      .finally(() => setExpLoading(false))
  }

  const fetchSummary = () => {
    setSumLoading(true)
    fetch(`${API}/summary`)
      .then(r => r.json())
      .then(data => setSummary(data.summary || ''))
      .catch(() => setSummary('Error fetching summary.'))
      .finally(() => setSumLoading(false))
  }

  useEffect(() => { fetchExplanation() }, [domain, role])
  useEffect(() => { fetchSummary() }, [])

  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight
  }, [messages])

  const sendMessage = async (q?: string) => {
    const question = q || input.trim()
    if (!question) return
    setInput('')
    const userMsg: Message = { role: 'user', content: question, ts: new Date().toLocaleTimeString() }
    setMessages(prev => [...prev, userMsg])
    setChatLoading(true)
    try {
      const r = await fetch(`${API}/chat?domain=${domain}&question=${encodeURIComponent(question)}`, { method: 'POST' })
      const data = await r.json()
      setMessages(prev => [...prev, { role: 'assistant', content: data.answer || 'No response.', ts: new Date().toLocaleTimeString() }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error connecting to backend.', ts: new Date().toLocaleTimeString() }])
    }
    setChatLoading(false)
  }

  return (
    <main className="pt-24 pb-margin px-margin max-w-[1600px] mx-auto w-full flex flex-col gap-lg">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="font-h1 text-h1 text-primary flex items-center gap-3">
            <span className="material-symbols-outlined text-[32px] text-[#4ade80]">psychology</span>
            GenAI Decision Intelligence
          </h1>
          <p className="text-on-surface-variant mt-1">Executive insights, conversational AI analysis, and daily system summaries via GPT-4o.</p>
        </div>
        <div className="flex gap-3 flex-wrap">
          <select value={role} onChange={e => setRole(e.target.value)}
            className="bg-surface border border-surface-variant text-primary font-label-caps text-label-caps px-4 py-2 uppercase outline-none">
            <option value="executive">Executive</option>
            <option value="data_scientist">Data Scientist</option>
            <option value="product_manager">Product Manager</option>
            <option value="operations">Operations</option>
          </select>
          <select value={domain} onChange={e => setDomain(e.target.value)}
            className="bg-surface border border-surface-variant text-primary font-label-caps text-label-caps px-4 py-2 uppercase outline-none">
            {DOMAINS.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <button onClick={fetchExplanation} className="px-5 py-2 bg-primary text-[#0A0A0A] font-label-caps text-label-caps hover:bg-zinc-200 transition-colors uppercase">
            Regenerate
          </button>
        </div>
      </div>

      {/* Daily Summary */}
      <div className="bg-[#0A0F0A] border border-[#22C55E]/30 p-lg relative">
        <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-[#22C55E] to-transparent"></div>
        <div className="flex items-center gap-3 mb-4 pb-3 border-b border-[#262626]">
          <span className="material-symbols-outlined text-[#22C55E] text-[18px]">summarize</span>
          <span className="font-label-caps text-[10px] text-zinc-400 uppercase tracking-widest">Daily Executive Summary — All Domains</span>
          <button onClick={fetchSummary} className="ml-auto text-zinc-500 hover:text-white transition-colors">
            <span className="material-symbols-outlined text-[16px]">refresh</span>
          </button>
        </div>
        {sumLoading ? (
          <div className="flex items-center gap-3 text-zinc-500"><span className="material-symbols-outlined animate-spin text-[16px]">sync</span> Generating summary...</div>
        ) : (
          <div className="font-body-base text-body-base text-primary leading-relaxed whitespace-pre-wrap" dangerouslySetInnerHTML={{ __html: summary.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br/>') }} />
        )}
      </div>

      {/* Two-column layout: Explanation + Chat */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-md">

        {/* Deep Insight Panel */}
        <div className="bg-surface border border-surface-variant relative flex flex-col">
          <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-[#4ade80] to-transparent"></div>
          <div className="p-md border-b border-[#262626] flex items-center gap-3">
            <span className="material-symbols-outlined text-zinc-400 text-[18px]">auto_awesome</span>
            <span className="font-label-caps text-[10px] text-zinc-400 uppercase tracking-widest">Deep-Dive Analysis · GPT-4o</span>
          </div>
          <div className="flex-1 p-lg min-h-[400px]">
            {expLoading ? (
              <div className="flex flex-col items-center justify-center h-full text-zinc-500 gap-3">
                <span className="material-symbols-outlined animate-spin text-[32px]">sync</span>
                <span className="font-label-caps tracking-widest text-sm">Analysing telemetry...</span>
              </div>
            ) : (
              <div className="font-body-base text-body-base text-primary leading-relaxed whitespace-pre-wrap text-sm"
                dangerouslySetInnerHTML={{ __html: explanation.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br/>') }} />
            )}
          </div>
        </div>

        {/* Conversational Chat */}
        <div className="bg-surface border border-surface-variant flex flex-col">
          <div className="p-md border-b border-[#262626] flex items-center gap-3">
            <span className="material-symbols-outlined text-zinc-400 text-[18px]">forum</span>
            <span className="font-label-caps text-[10px] text-zinc-400 uppercase tracking-widest">Ask Aether AI · Conversational Interface</span>
          </div>

          {/* Suggested Questions */}
          {messages.length === 0 && (
            <div className="p-4 border-b border-[#262626]">
              <div className="font-label-caps text-[10px] text-zinc-600 mb-2 uppercase">Suggested Questions</div>
              <div className="flex flex-wrap gap-2">
                {SUGGESTED_QUESTIONS.map(q => (
                  <button key={q} onClick={() => sendMessage(q)}
                    className="px-3 py-1.5 bg-[#1A1A1A] border border-[#262626] text-zinc-400 text-xs hover:border-zinc-500 hover:text-white transition-colors">
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Messages */}
          <div ref={chatRef} className="flex-1 overflow-y-auto p-4 flex flex-col gap-3 min-h-[300px] max-h-[400px]">
            {messages.map((m, i) => (
              <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
                <div className={`w-7 h-7 flex items-center justify-center flex-shrink-0 ${m.role === 'user' ? 'bg-zinc-700' : 'bg-[#4ade8020] border border-[#4ade8040]'}`}>
                  <span className="material-symbols-outlined text-[14px]">{m.role === 'user' ? 'person' : 'psychology'}</span>
                </div>
                <div className={`max-w-[80%] p-3 text-sm leading-relaxed ${m.role === 'user' ? 'bg-zinc-800 text-zinc-100' : 'bg-[#0A0F0A] border border-[#22C55E]/20 text-primary'}`}>
                  {m.content}
                  <div className="font-mono text-[10px] text-zinc-600 mt-1">{m.ts}</div>
                </div>
              </div>
            ))}
            {chatLoading && (
              <div className="flex gap-3">
                <div className="w-7 h-7 bg-[#4ade8020] border border-[#4ade8040] flex items-center justify-center">
                  <span className="material-symbols-outlined text-[14px] animate-spin">sync</span>
                </div>
                <div className="p-3 bg-[#0A0F0A] border border-[#22C55E]/20 text-zinc-500 text-sm">Thinking...</div>
              </div>
            )}
          </div>

          {/* Input */}
          <div className="p-4 border-t border-[#262626] flex gap-3">
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && sendMessage()}
              placeholder="Ask about model performance, drift, risk..."
              className="flex-1 bg-[#0A0A0A] border border-[#262626] text-primary px-4 py-2 text-sm outline-none placeholder:text-zinc-600 focus:border-zinc-500 transition-colors"
            />
            <button onClick={() => sendMessage()}
              className="px-5 py-2 bg-primary text-[#0A0A0A] font-label-caps text-label-caps hover:bg-zinc-200 transition-colors">
              <span className="material-symbols-outlined text-[16px]">send</span>
            </button>
          </div>
        </div>
      </div>
    </main>
  )
}
