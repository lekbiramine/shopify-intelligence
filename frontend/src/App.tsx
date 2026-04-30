import { useEffect, useMemo, useState } from 'react'
import { Link, Route, Routes, useNavigate, useParams, useSearchParams } from 'react-router-dom'

type Action = {
  id: string
  title: string
  value: number
  daily_loss: number
  priority_score: number
  priority_ratio: number
  priority_explanation: string
  rank: number
  context: string
  targets: string[]
  execute_command: string
  goal: string
  measured_by: string[]
  expected_result: {
    metric: string
    baseline: number
    target: number
    time_window_days: number
  }
  baseline_metrics: {
    orders_7d: number
    revenue_7d: number
  }
  normalized_impact_weight: number
}

type ResultsData = {
  completed_actions: Array<{
    action_id: string
    title: string
    timestamp_started: string
    timestamp_completed: string
    baseline_metrics: { orders_7d: number; revenue_7d: number }
    value: number
    daily_loss: number
  }>
  before_after_comparison: Array<{
    action_id: string
    title: string
    status: 'validated' | 'pending_validation'
    before: { orders_7d: number; revenue_7d: number }
    after: { orders_7d: number; revenue_7d: number }
    delta: { orders_7d: number; revenue_7d: number }
    raw_delta: { orders_7d: number; revenue_7d: number }
    normalized_delta: { orders_7d: number; revenue_7d: number }
    impact_score: number
    expected_result: {
      metric: string
      baseline: number
      target: number
      time_window_days: number
    }
    timestamp_started: string
    timestamp_completed: string
  }>
  total_revenue_recovered_7d: number
  total_loss_prevented_7d: number
  roi_efficiency_score: number
}

type ProofRow = {
  action_id: string
  is_valid: boolean
  confidence_score: number
  predicted_delta: { orders: number; revenue: number }
  actual_delta: { orders: number; revenue: number }
  roi_confirmed: boolean
}

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

function currency(value: number): string {
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function useActions(storeId: number) {
  const [actions, setActions] = useState<Action[]>([])
  const [loading, setLoading] = useState(true)

  async function loadActions() {
    setLoading(true)
    const response = await fetch(`${apiBase}/api/actions?store_id=${storeId}`)
    const data: Action[] = await response.json()
    setActions(data)
    setLoading(false)
  }

  useEffect(() => {
    void loadActions()
  }, [storeId])

  return { actions, loading, reload: loadActions }
}

function useResults(storeId: number) {
  const [data, setData] = useState<ResultsData | null>(null)
  const [proof, setProof] = useState<ProofRow[]>([])

  useEffect(() => {
    fetch(`${apiBase}/api/results?store_id=${storeId}`)
      .then((res) => res.json())
      .then((json: ResultsData) => setData(json))
    fetch(`${apiBase}/api/proof?store_id=${storeId}`)
      .then((res) => res.json())
      .then((json: ProofRow[]) => setProof(json))
  }, [storeId])

  return { data, proof }
}

function DashboardPage() {
  const [search] = useSearchParams()
  const storeId = Number(search.get('store_id') || '1')
  const navigate = useNavigate()
  const { actions, loading, reload } = useActions(storeId)
  const stats = useMemo(() => {
    const dailyLoss = actions.reduce((sum, a) => sum + a.daily_loss, 0)
    const recoverable = actions.reduce((sum, a) => sum + a.value, 0)
    return { dailyLoss, recoverable, pending: actions.length }
  }, [actions])

  async function markDone(actionId: string) {
    await fetch(`${apiBase}/api/complete-action?store_id=${storeId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action_id: actionId }),
    })
    await reload()
  }

  return (
    <div className="page">
      <div className="banner">EXECUTE ACTION #1 NOW</div>
      <section className="control-center">
        <article><h4>You are losing</h4><p>{currency(stats.dailyLoss)}/day</p></article>
        <article><h4>Recoverable today</h4><p>{currency(stats.recoverable)}</p></article>
        <article><h4>Actions pending</h4><p>{stats.pending}</p></article>
      </section>
      <div className="nav-row">
        <Link to={`/results?store_id=${storeId}`}>Results</Link>
        <Link to={`/progress?store_id=${storeId}`}>Progress</Link>
      </div>
      {loading && <p>Loading actions...</p>}
      <div className="grid">
        {actions.map((action) => (
          <article key={action.id} className="card">
            <h3>{action.title}</h3>
            <p>Value: {currency(action.value)}</p>
            <p>Daily Loss: {currency(action.daily_loss)}</p>
            <p>Priority Score: {action.priority_score.toFixed(2)}</p>
            <p className="small">{action.context}</p>
            <p className="small">{action.priority_explanation}</p>
            <div className="btn-row">
              <button type="button" onClick={() => navigate(`/action/${action.id}?store_id=${storeId}`)}>VIEW</button>
              <button type="button" onClick={() => void markDone(action.id)}>MARK AS DONE</button>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

function ActionPage() {
  const [search] = useSearchParams()
  const storeId = Number(search.get('store_id') || '1')
  const { id } = useParams()
  const { actions } = useActions(storeId)
  const action = actions.find((x) => x.id === id)
  if (!action) return <div className="page">Action not found.</div>

  return (
    <div className="page">
      <Link to={`/dashboard?store_id=${storeId}`}>Back</Link>
      <h2>{action.title}</h2>
      <p><strong>Why this matters:</strong> {action.context}</p>
      <p><strong>Targets:</strong> {action.targets.join(' | ')}</p>
      <p><strong>Exact execution:</strong> {action.execute_command}</p>
      <p><strong>Goal:</strong> reach {action.expected_result.target} {action.expected_result.metric} in {action.expected_result.time_window_days} days</p>
      <p><strong>Measured by:</strong> {action.measured_by.join(', ')}</p>
    </div>
  )
}

function ResultsPage() {
  const [search] = useSearchParams()
  const storeId = Number(search.get('store_id') || '1')
  const { data, proof } = useResults(storeId)
  if (!data) return <div className="page">Loading results...</div>
  const proofByAction = new Map(proof.map((p) => [p.action_id, p]))

  return (
    <div className="page">
      <Link to={`/dashboard?store_id=${storeId}`}>Back</Link>
      <h2>Results</h2>
      <section className="card">
        <h3>System Impact This Week</h3>
        <p>Total Revenue Recovered (7d): {currency(data.total_revenue_recovered_7d)}</p>
        <p>Total Loss Prevented (7d): {currency(data.total_loss_prevented_7d)}</p>
        <p>ROI Efficiency Score: {data.roi_efficiency_score.toFixed(2)}</p>
      </section>
      {data.before_after_comparison.map((row) => {
        const p = proofByAction.get(row.action_id)
        if (!p) return null
        const isValidated = row.status === 'validated'
        return (
          <article key={row.action_id} className="card">
            <p><strong>{row.title}</strong></p>
            {isValidated ? (
              <>
                <p><strong style={{ color: '#15803d' }}>ROI CONFIRMED</strong></p>
                <p>Before: {row.before.orders_7d} orders / {currency(row.before.revenue_7d)}</p>
                <p>After: {row.after.orders_7d} orders / {currency(row.after.revenue_7d)}</p>
                <p>Delta: {row.raw_delta.orders_7d} orders / {currency(row.raw_delta.revenue_7d)}</p>
                <p>Confidence score: {p.confidence_score.toFixed(2)}</p>
              </>
            ) : (
              <>
                <p><strong style={{ color: '#ca8a04' }}>IMPACT IN PROGRESS</strong></p>
                <p>Baseline: {row.before.orders_7d} orders / {currency(row.before.revenue_7d)}</p>
                <p>
                  Expected result: {row.expected_result.target} {row.expected_result.metric} in{' '}
                  {row.expected_result.time_window_days} days
                </p>
                <p className="small">Waiting for 24h validation window</p>
              </>
            )}
          </article>
        )
      })}
    </div>
  )
}

function ProgressPage() {
  const [search] = useSearchParams()
  const storeId = Number(search.get('store_id') || '1')
  const { data } = useResults(storeId)
  if (!data) return <div className="page">Loading progress...</div>
  return (
    <div className="page">
      <Link to={`/dashboard?store_id=${storeId}`}>Back</Link>
      <h2>Progress</h2>
      <p>Actions completed: {data.completed_actions.length}</p>
      <p>Total revenue recovered (7d): {currency(data.total_revenue_recovered_7d)}</p>
      <p>Total loss prevented (7d): {currency(data.total_loss_prevented_7d)}</p>
      <p>ROI efficiency score: {data.roi_efficiency_score.toFixed(2)}</p>
    </div>
  )
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<DashboardPage />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/action/:id" element={<ActionPage />} />
      <Route path="/results" element={<ResultsPage />} />
      <Route path="/progress" element={<ProgressPage />} />
    </Routes>
  )
}

export default App
