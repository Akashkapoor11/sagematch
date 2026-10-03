import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getJSON, uploadCatalogue } from './api.js'

const QUICK_CASES = [
  ['CRM + Slack', 'I need a CRM for a 20-person sales team that integrates with Slack.'],
  ['Projects + Jira', 'We need project management software for a team of 30 with Jira integration and Kanban.'],
  ['Self-hosted BI', 'I need self-hosted analytics with dashboards for 50 users.'],
  ['Ambiguous request', 'I need software for my business.'],
  ['CRM without Slack', 'We need a CRM that does not use Slack — our team uses Microsoft Teams only.'],
  ['HR + budget', 'Looking for an affordable HR platform for a 50-person company with approvals and Slack.'],
  ['DevOps + GitHub', 'We need a DevOps workspace with GitHub integration and workflow automation for an engineering team of 100.'],
  ['Helpdesk + tickets', 'We need helpdesk software for 40 users with ticketing and knowledge base capabilities.'],
]

function App() {
  const [query, setQuery] = useState('')
  const [answers, setAnswers] = useState({})
  const [probes, setProbes] = useState([])
  const [result, setResult] = useState(null)
  const [health, setHealth] = useState({ label: 'checking system…', good: false })
  const [stats, setStats] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [traceOpen, setTraceOpen] = useState(false)
  const [activeChip, setActiveChip] = useState(null)
  const queryId = useRef(0)

  const refresh = useCallback(async () => {
    try {
      const [h, s] = await Promise.all([getJSON('/api/health'), getJSON('/api/catalog/stats')])
      setHealth({ label: `${h.products} products ready`, good: true })
      setStats(s)
    } catch (err) {
      setHealth({ label: 'system unavailable', good: false })
      setError(err.message)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const runQuery = useCallback(async (nextAnswers = answers, inputQuery = query) => {
    const trimmed = inputQuery.trim()
    if (!trimmed) return
    const requestId = ++queryId.current
    setBusy(true)
    setError('')
    try {
      const res = await getJSON('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: trimmed, answers: nextAnswers, top_k: 3 }),
      })
      if (requestId !== queryId.current) return
      setResult(res)
      setProbes(res.status === 'needs_clarification' ? (res.probes || []) : [])
      if (res.status === 'complete') setTraceOpen(false)
    } catch (err) {
      if (requestId === queryId.current) setError(err.message)
    } finally {
      if (requestId === queryId.current) setBusy(false)
    }
  }, [answers, query])

  const freshQuery = () => {
    setAnswers({})
    setProbes([])
    setResult(null)
    setError('')
    setTraceOpen(false)
    setActiveChip(null)
  }

  const submitProbeAnswers = () => {
    const collected = { ...answers }
    for (const probe of probes) {
      const value = document.querySelector(`[data-probe-field="${CSS.escape(probe.field)}"]`)?.value?.trim()
      if (value) collected[probe.field] = value
    }
    setAnswers(collected)
    runQuery(collected)
  }

  const onQuerySubmit = () => {
    setAnswers({})
    setProbes([])
    runQuery({})
  }

  const onChip = (label, value) => {
    freshQuery()
    setQuery(value)
    setActiveChip(label)
    void runQuery({}, value)
  }

  const resetDemo = async () => {
    setBusy(true)
    setError('')
    try {
      await getJSON('/api/catalog/reset-demo', { method: 'POST' })
      freshQuery()
      await refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const onUpload = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    setBusy(true)
    setError('')
    try {
      await uploadCatalogue(file)
      await refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      event.target.value = ''
      setBusy(false)
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="logo">S</div>
          <div><strong>SageMatch</strong><span>Grounded Software Advisor · React</span></div>
        </div>
        <div className="status"><span className="dot" style={{ background: health.good ? '#59d3a5' : '#f5c36b' }} />{health.label}</div>
      </header>

      <main className="page">
        <section className="hero">
          <div>
            <div className="eyebrow">ZOFTWARE HIREATHON · DECISION ENGINE</div>
            <h1>From messy catalogue data to recommendations you can defend.</h1>
            <p>Clean the data. Discover what the buyer really needs. Filter hard constraints. Rank the best three. Show the evidence.</p>
          </div>
          <div className="hero-badge"><span>TOP 3</span><small>evidence-backed recommendations</small></div>
        </section>

        <section className="workspace">
          <div className="panel query-panel">
            <div className="panel-head">
              <div><h2>Find the right software</h2><p>Use a real customer request, not a keyword query.</p></div>
              <button className="ghost" onClick={resetDemo} disabled={busy}>Reset demo</button>
            </div>
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') onQuerySubmit() }}
              placeholder="Example: I need a CRM for a 20-person sales team that integrates with Slack."
              aria-label="Customer software requirement"
            />
            <div className="chips">
              {QUICK_CASES.map(([label, value]) => <button className={`chip${activeChip === label ? ' chip--active' : ''}`} key={label} onClick={() => onChip(label, value)} disabled={busy}>{label}</button>)}
            </div>
            <button className="primary" onClick={onQuerySubmit} disabled={busy || !query.trim()}>
              {busy ? 'Analyzing…' : <>Analyze requirements <span>→</span></>}
            </button>
            {error && <div className="error-banner" role="alert">{error}</div>}

            {probes.length > 0 && (
              <section className="probe" aria-live="polite">
                <div className="probe-head">
                  <div><span className="eyebrow">PROBING LAYER</span><h3>Answer only what changes the decision</h3></div>
                  <span className="impact-label">high-impact questions</span>
                </div>
                {probes.map((probe) => (
                  <div className="probe-row" key={probe.id}>
                    <label htmlFor={`probe-${probe.id}`}>
                      <strong>{probe.question}</strong>
                      <small>{probe.why_it_matters}</small>
                      <span className="impact">Expected decision impact {Math.round((probe.expected_impact || 0) * 100)}%</span>
                    </label>
                    <div>
                      {probe.options?.length ? (
                        <select id={`probe-${probe.id}`} data-probe-field={probe.field} defaultValue="">
                          <option value="">Select…</option>
                          {probe.options.map((o) => <option key={o} value={o}>{o}</option>)}
                        </select>
                      ) : (
                        <input id={`probe-${probe.id}`} data-probe-field={probe.field} placeholder="Your answer" inputMode={probe.field === 'team_size' ? 'numeric' : undefined} />
                      )}
                    </div>
                  </div>
                ))}
                <button className="primary" onClick={submitProbeAnswers} disabled={busy}>Refine recommendation <span>→</span></button>
              </section>
            )}
          </div>

          <aside className="panel quality-panel">
            <div className="panel-head"><div><h2>Data quality</h2><p>Audit before recommendations.</p></div><span className="rubric">RUBRIC 01</span></div>
            <div className="quality-score"><div>{stats?.quality_score ?? '—'}</div><span>/100 catalogue health</span></div>
            <div className="stats">
              {[
                [stats?.products ?? '—', 'products ingested'],
                [Object.keys(stats?.categories || {}).length, 'categories'],
                [stats?.integrations ?? '—', 'integrations'],
                [stats?.features ?? '—', 'feature signals'],
                [stats?.deployment_models ?? '—', 'deployment models'],
                [stats?.quality_report?.duplicates_removed ?? 0, 'duplicates removed'],
              ].map(([value, label]) => <div className="stat" key={label}><b>{value}</b><span>{label}</span></div>)}
            </div>
            <label className="upload">
              <input type="file" accept=".csv,.json" onChange={onUpload} disabled={busy} />
              <span>Replace catalogue</span><small>CSV or JSON · sanitized on ingest</small>
            </label>
          </aside>
        </section>

        {result?.status === 'complete' && <Results result={result} traceOpen={traceOpen} setTraceOpen={setTraceOpen} />}
      </main>
    </div>
  )
}

function Results({ result, traceOpen, setTraceOpen }) {
  const confidence = Math.round((result.needs?.confidence || 0) * 100)
  const relaxed = Boolean(result.trace?.relaxed_constraints)
  return (
    <>
      <section className="panel results-panel">
        <div className="panel-head">
          <div><div className="eyebrow">RANKED OUTPUT</div><h2>Recommendations</h2><p>Evidence-weighted matches from the sanitized catalogue.</p></div>
          <div className="pill">Requirement confidence {confidence}%</div>
        </div>
        <div className="requirements">{requirementTags(result.needs)}</div>
        <div className={relaxed ? 'notice warning' : 'notice'}>
          {relaxed ? 'The catalogue cannot satisfy every hard requirement with 3 products, so fallback matches are shown transparently.' : 'All three recommendations satisfy the available hard constraints.'}
        </div>
        <div className="cards">
          {result.recommendations.map((recommendation) => <RecommendationCard key={recommendation.product.id} recommendation={recommendation} />)}
        </div>
      </section>
      <button id="trace-toggle-btn" className="trace-toggle" onClick={() => setTraceOpen((v) => !v)}>{traceOpen ? 'Hide decision trace' : 'Show decision trace'}</button>
      {traceOpen && <section className="trace" aria-live="polite"><span>Decision trace</span> {result.trace?.catalog_size || 0} products → requirements → probing → hard-constraint filtering → evidence ranking → grounded explanation → {result.trace?.api_policy_summary || 'API-assisted AI'}.</section>}
    </>
  )
}

function requirementTags(needs) {
  return [
    needs?.category && `Category: ${needs.category}`,
    needs?.team_size != null && `Team size: ${needs.team_size}`,
    ...(needs?.integrations || []).map((x) => `Integration: ${x}`),
    ...(needs?.excluded_integrations || []).map((x) => `Without: ${x}`),
    ...(needs?.deployment || []).map((x) => `Deployment: ${x}`),
    ...(needs?.features || []).map((x) => `Feature: ${x}`),
    needs?.pricing_tier && `Pricing: ${needs.pricing_tier}`,
    needs?.budget_text && `Budget note: ${needs.budget_text}`,
  ].filter(Boolean).map((tag) => <span className="req" key={tag}>{tag}</span>)
}

function RecommendationCard({ recommendation }) {
  const r = recommendation
  const score = Math.round(r.score * 100)
  const breakdown = useMemo(() => Object.entries(r.score_breakdown || {}), [r.score_breakdown])
  return (
    <article className={`card ${r.hard_constraints_satisfied ? '' : 'relaxed'}`}>
      <div className="rank"><div className="rank-badge">#{r.rank} · {r.product.category}</div><div className="score">{score}<span>/100</span></div></div>
      <h3>{r.product.name}</h3>
      <div className="category">{r.product.description || 'No description available.'}</div>
      <div className="scorebar"><span style={{ width: `${score}%` }} /></div>
      <div className="why"><h4>Why it fits</h4>{r.why_recommended.map((text, i) => <div key={`${text}-${i}`}>{text}</div>)}</div>
      <div className="improve"><h4>Improve the fit</h4>{r.improve_fit.map((text, i) => <div key={`${text}-${i}`}>{text}</div>)}</div>
      <details>
        <summary>Decision evidence &amp; score</summary>
        <div className="evidence-list">{r.evidence.map((e, i) => <div className={`evidence-row ${e.status}`} key={`${e.field}-${i}`}><span>{e.status === 'matched' ? '✓' : e.status === 'partial' ? '◐' : '×'}</span><div><strong>{e.requirement}</strong><small>{e.evidence}{e.source_row != null ? ` · source row ${e.source_row}` : ''}</small></div></div>)}</div>
        <div className="breakdown">{breakdown.map(([key, value]) => <span key={key}>{key} <b>{Math.round(value * 100)}%</b></span>)}</div>
      </details>
    </article>
  )
}

export default App
