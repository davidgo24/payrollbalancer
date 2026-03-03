import { useState, useCallback } from 'react'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || ''

function App() {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [currentIdx, setCurrentIdx] = useState(0)
  const [edits, setEdits] = useState({}) // { empId: { "date_code": hrs } }

  const handleUpload = useCallback(async (e) => {
    e.preventDefault()
    const tcp = e.target.tcp?.files?.[0]
    const accrual = e.target.accrual?.files?.[0]
    if (!tcp || !accrual) {
      setError('Please select both TCP CSV and Accrual Excel')
      return
    }
    setLoading(true)
    setError(null)
    const fd = new FormData()
    fd.append('file_tcp', tcp)
    fd.append('file_accrual', accrual)
    try {
      const res = await fetch(`${API_URL}/api/run`, { method: 'POST', body: fd })
      if (!res.ok) {
        const err = await res.text()
        throw new Error(err)
      }
      const data = await res.json()
      setResult(data)
      setCurrentIdx(0)
      setEdits({})
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  const getCellValue = (emp, date, code) => {
    const key = `${emp.emp_id}_${date}_${code}`
    if (edits[key] !== undefined) return edits[key]
    const dayRow = emp.grid.days.find((d) => d.date === date)
    return dayRow?.cells?.[code] ?? ''
  }

  const setCellValue = (empId, date, code, value) => {
    const key = `${empId}_${date}_${code}`
    const v = value === '' ? '' : parseFloat(value)
    if (isNaN(v) && value !== '') return
    setEdits((prev) => ({ ...prev, [key]: v }))
  }

  const buildExportData = () => {
    if (!result) return []
    const rows = []
    const allCodes = result.allCodes || []
    for (const emp of result.employees) {
      const codes = [...new Set([...emp.grid.codes, ...allCodes])]
      for (const day of emp.grid.days) {
        for (const code of codes) {
          const val = getCellValue(emp, day.date, code)
          if (val !== '' && val !== undefined && !isNaN(val) && Number(val) > 0) {
            rows.push({ emp_id: emp.emp_id, hrs: Number(val), code, date: day.date })
          }
        }
      }
    }
    return rows
  }

  const downloadCSV = () => {
    const rows = buildExportData()
    const lines = rows.map((r) => `${r.emp_id},${r.hrs},${r.code},${r.date}`)
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'suggested_rebalancing.csv'
    a.click()
    URL.revokeObjectURL(a.href)
  }

  if (!result) {
    return (
      <div className="app">
        <header>
          <h1>Payroll Balancer</h1>
          <p>Pre-validate TCP hours before New World · One employee at a time</p>
        </header>
        <section className="upload-section">
          <form onSubmit={handleUpload}>
            <div className="dropzone-row">
              <label>
                <span>TCP Export (CSV)</span>
                <input type="file" name="tcp" accept=".csv,.txt" required />
              </label>
              <label>
                <span>Accrual Balance Report (Excel)</span>
                <input type="file" name="accrual" accept=".xlsx,.xls" required />
              </label>
            </div>
            <button type="submit" disabled={loading}>
              {loading ? 'Running...' : 'Run Balancer'}
            </button>
          </form>
        </section>
        {error && <div className="error">{error}</div>}
      </div>
    )
  }

  const employees = result.employees
  const emp = employees[currentIdx]
  const allCodes = result.allCodes && result.allCodes.length ? result.allCodes : (emp?.grid?.codes || [])

  return (
    <div className="app">
      <header>
        <h1>Payroll Balancer</h1>
        <p>{result.dateRange}</p>
      </header>

      <section className="employee-nav">
        <button onClick={() => setCurrentIdx((i) => Math.max(0, i - 1))} disabled={currentIdx === 0}>
          ← Previous
        </button>
        <select
          value={currentIdx}
          onChange={(e) => setCurrentIdx(Number(e.target.value))}
          className="emp-select"
        >
          {employees.map((e, i) => (
            <option key={e.emp_id} value={i}>
              {e.emp_id} {e.name}
            </option>
          ))}
        </select>
        <button onClick={() => setCurrentIdx((i) => Math.min(employees.length - 1, i + 1))} disabled={currentIdx === employees.length - 1}>
          Next →
        </button>
        <span className="emp-counter">
          {currentIdx + 1} of {employees.length}
        </span>
      </section>

      <section className="employee-view">
        <h2>
          {emp.emp_id} {emp.name}
        </h2>
        <div className="totals-bar">
          <div><strong>Regular</strong> {emp.totals?.reg?.toFixed(2) ?? '-'}</div>
          <div><strong>Premium (OT)</strong> {emp.totals?.ot?.toFixed(2) ?? '-'}</div>
          <div><strong>Reg + Premium</strong> {emp.totals?.reg_plus_ot?.toFixed(2) ?? '-'}</div>
          <div><strong>LWOP</strong> {emp.totals?.lwop?.toFixed(2) ?? '-'}</div>
        </div>

        <div className="grid-wrap">
          <table className="hours-grid">
            <thead>
              <tr>
                <th>Date</th>
                <th>Day</th>
                {allCodes.map((code) => (
                  <th key={code}>{code}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {emp.grid.days.map((day) => (
                <tr key={day.date}>
                  <td>{day.date}</td>
                  <td>{day.day}</td>
                  {allCodes.map((code) => (
                    <td key={code}>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={getCellValue(emp, day.date, code)}
                        onChange={(e) => setCellValue(emp.emp_id, day.date, code, e.target.value)}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {emp.actions?.length > 0 && (
          <details className="change-log">
            <summary>Proposed changes ({emp.actions.length})</summary>
            <ul>
              {emp.actions.map((a, i) => (
                <li key={i}>{a.original_hrs} {a.original_code} → {a.proposed_code}: {a.reason}</li>
              ))}
            </ul>
          </details>
        )}
      </section>

      <section className="footer-actions">
        <button onClick={downloadCSV}>Download CSV</button>
      </section>
    </div>
  )
}

export default App
