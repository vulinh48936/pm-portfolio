import { useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import type {
  Metrics, WeightGridResult, Feasibility, AttributionResult,
  LiquidityResult, LiqEventRow, LabConfig, StrategySpec, StrategyExplanation,
} from './types'
import { runLiquidity } from './api'

// Chart palette from the VPS design system; do not introduce colours outside it.
export const COLORS = ['#8229E3', '#041361', '#7FD08C', '#87B4DD', '#6F41AD', '#EACACF']
export const CHART_INK = '#1E1E1E'     // main benchmark line
export const CHART_MUTED = '#B8BABC'   // secondary reference line

/** Official VPS logo, inlined so it can be recoloured for the background: all-white on
 *  violet, wordmark #38383D with a violet icon on light. Never rescale the parts or add
 *  an outline or shadow. The original file is in `public/vps-logo.svg`. */
export function VpsLogo({ onViolet = true, height = 28 }: { onViolet?: boolean; height?: number }) {
  const word = onViolet ? '#FFFFFF' : '#38383D'
  const icon = onViolet ? '#FFFFFF' : '#8229E3'
  return (
    <svg height={height} viewBox="0 0 73 28" fill="none" role="img" aria-label="VPS"
      style={{ width: (73 / 28) * height }}>
      <path d="M16.6206 6.36403H13.3405C13.1281 6.36403 12.9659 6.48867 12.9195 6.67565L8.62241 19.4953L4.58248 6.68856C4.53272 6.48811 4.37003 6.36403 4.15758 6.36403H0.38601C0.242885 6.36403 0.11765 6.42916 0.0505603 6.53865C-0.0109387 6.63915 -0.0154114 6.76043 0.0321106 6.85195L5.93099 23.3387C5.98075 23.5391 6.14344 23.6632 6.35533 23.6632H10.5865C10.7989 23.6632 10.9616 23.5386 11.0063 23.355L16.9678 6.86992C17.0226 6.75987 17.0187 6.63859 16.9566 6.53808C16.8896 6.4286 16.7638 6.36346 16.6212 6.36346L16.6206 6.36403Z" fill={word} />
      <path d="M27.559 6.0343C25.5005 6.0343 23.8411 6.82093 22.6184 8.31615L22.61 6.76254C22.61 6.53907 22.4356 6.36389 22.2131 6.36389H18.7037C18.4812 6.36389 18.3068 6.53907 18.3068 6.76366L18.3722 16.3139L18.3068 27.6013C18.3068 27.8248 18.4812 27.9999 18.7037 27.9999H22.2461C22.4686 27.9999 22.643 27.8248 22.643 27.5996L22.6469 21.9416C23.8294 23.3279 25.4412 23.9927 27.4612 23.9927C31.827 23.9927 34.8768 20.2796 34.8768 14.9641C34.8768 9.64855 32.0048 6.0343 27.5596 6.0343H27.559ZM26.4112 20.9556C25.406 20.9556 24.5718 20.6266 23.9311 19.9781C22.9404 18.9747 22.4266 17.2072 22.4462 14.8669C22.4775 11.0972 23.8719 9.10447 26.4772 9.10447C28.316 9.10447 30.5082 10.1612 30.5082 15.1948C30.5082 18.9101 29.0534 20.9562 26.4118 20.9562L26.4112 20.9556Z" fill={word} />
      <path d="M51.5587 18.4886C51.5587 21.8524 48.5184 24.0242 43.8137 24.0242C39.109 24.0242 36.5182 22.2668 35.9513 19.0428C35.9083 18.7974 36.0972 18.5711 36.3455 18.5711H39.7559C39.9376 18.5711 40.0964 18.6958 40.1405 18.8732C40.5324 20.4448 41.7949 21.1848 44.0435 21.1848C46.2921 21.1848 47.4511 20.3235 47.4511 18.8187C47.4511 17.314 45.4719 16.9574 43.1808 16.5812C40.0874 16.0742 36.2359 15.4431 36.2359 11.3073C36.2359 7.93613 38.853 6.00183 43.4201 6.00183C47.4108 6.00183 50.019 7.53635 50.7642 10.2623C50.8296 10.501 50.6457 10.7368 50.3997 10.7368H47.0077C46.8629 10.7368 46.7271 10.6554 46.6689 10.5223C46.1691 9.37127 45.0414 8.77329 43.3547 8.77329C41.9799 8.77329 40.3412 9.16914 40.3412 11.045C40.3412 12.4965 42.265 12.7901 44.493 13.1298C47.6417 13.6104 51.5592 14.2073 51.5592 18.4886H51.5587Z" fill={word} />
      <path d="M62.3236 0H55.8875V4.31553H67.3967C68.1347 4.31553 68.7329 4.92698 68.7329 5.68105V17.2666H72.9998V10.722C72.9998 4.80009 68.2197 0 62.3236 0Z" fill={icon} />
      <path d="M55.8885 6.46173V10.7183H61.2093C61.8881 10.7183 62.4382 11.2803 62.4382 11.9743V17.2668H66.6481C66.6056 11.3174 61.8126 6.5044 55.8885 6.46173Z" fill={icon} />
    </svg>
  )
}

export function StatusDot({ ok }: { ok: boolean }) {
  return <span className={`inline-block w-2.5 h-2.5 rounded-full ${ok ? 'bg-vps-green' : 'bg-vps-red'} ring-2 ring-white`} />
}

// Strategy explanation box
const ROLE_STYLE: Record<string, { border: string; tag: string; label: string }> = {
  risk: { border: 'border-vps-red', tag: 'bg-vps-red text-vps-deep', label: 'Rủi ro' },
  return: { border: 'border-vps-green', tag: 'bg-vps-green text-vps-black', label: 'Lợi nhuận' },
  rebalance: { border: 'border-vps-blue', tag: 'bg-vps-blue text-vps-black', label: 'Tái cân bằng' },
  other: { border: 'border-vps-gray', tag: 'bg-vps-offwhite text-vps-black', label: '—' },
}

export function StrategyExplanationBox(
  { explanation, loading }: { explanation: StrategyExplanation | null; loading?: boolean },
) {
  if (loading) return <p className="text-xs text-vps-gray">Đang giải thích chiến lược…</p>
  if (!explanation) return null
  const e = explanation
  return (
    <div className="bg-vps-lavender/40 border border-vps-lavender rounded-vps p-3 space-y-2">
      <div>
        <div className="text-sm font-semibold text-vps-black tracking-vps">📘 {e.title}</div>
        <p className="text-xs text-vps-black/80 mt-0.5">{e.summary}</p>
      </div>
      <div className="space-y-1.5">
        {e.components.map((c, i) => {
          const st = ROLE_STYLE[c.role] ?? ROLE_STYLE.other
          return (
            <div key={i} className={`border-l-2 ${st.border} pl-2 py-0.5`}>
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-xs font-semibold text-vps-black">{c.label}</span>
                {c.role !== 'other' && (
                  <span className={`text-[9px] px-1 rounded ${st.tag}`}>{st.label}</span>
                )}
              </div>
              {c.formula && (
                <code className="block text-[11px] font-mono bg-white text-vps-deep border border-vps-lavender rounded px-1.5 py-0.5 my-0.5 overflow-x-auto">
                  {c.formula}
                </code>
              )}
              <p className="text-[11px] text-vps-black/80">{c.meaning}</p>
            </div>
          )
        })}
      </div>
      <div className="text-[11px] text-vps-black/80">
        <span className="font-semibold text-vps-deep">Rebalance: </span>{e.rebalance}
      </div>
      {e.recommendations?.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {e.recommendations.map((r, i) => (
            <span key={i} className="text-[10px] bg-white border border-vps-lavender rounded px-1.5 py-0.5 text-vps-deep">{r}</span>
          ))}
        </div>
      )}
    </div>
  )
}

// Multi-line chart: equity curves, max weight
export function MultiLineChart({
  dates, series, height = 300, yLabel, refLine,
}: {
  dates: string[]
  series: { name: string; values: number[]; color?: string; dashed?: boolean }[]
  height?: number
  yLabel?: string
  refLine?: number
}) {
  const step = Math.max(1, Math.floor(dates.length / 350))
  // Keys are `s0, s1...`, not the series name: recharts treats dataKey as a lodash path,
  // so a strategy name containing a dot would silently drop the line.
  const data = dates.filter((_, i) => i % step === 0).map((d, j) => {
    const i = j * step
    const row: Record<string, number | string> = { date: d }
    series.forEach((s, k) => { row[`s${k}`] = Math.round(s.values[i] * 100) / 100 })
    return row
  })
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E0DCF4" />
        <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#1E1E1E' }} stroke="#B8BABC" minTickGap={40} />
        <YAxis tick={{ fontSize: 10, fill: '#1E1E1E' }} stroke="#B8BABC" width={48}
          label={yLabel ? { value: yLabel, angle: -90, position: 'insideLeft', fontSize: 11 } : undefined} />
        <Tooltip contentStyle={{ fontSize: 12, borderRadius: 10, borderColor: '#E0DCF4' }} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {refLine !== undefined && (
          <Line dataKey={() => refLine} name={`cap ${refLine}%`} stroke="#B8BABC"
            strokeDasharray="4 4" dot={false} isAnimationActive={false} />
        )}
        {series.map((s, i) => (
          <Line key={`s${i}`} type="monotone" dataKey={`s${i}`} name={s.name}
            stroke={s.color ?? COLORS[i % COLORS.length]} strokeWidth={2}
            strokeDasharray={s.dashed ? '5 4' : undefined}
            dot={false} isAnimationActive={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}

// Metric cards
const METRIC_DISPLAY: { key: string; label: string; suffix?: string; good?: 'hi' | 'lo' }[] = [
  { key: 'final', label: 'Final (base 100)' },
  { key: 'ann_ret_pct', label: 'Return/năm', suffix: '%', good: 'hi' },
  { key: 'ann_vol_pct', label: 'Vol/năm', suffix: '%', good: 'lo' },
  { key: 'sharpe', label: 'Sharpe', good: 'hi' },
  { key: 'sortino', label: 'Sortino', good: 'hi' },
  { key: 'maxdd_pct', label: 'Max Drawdown', suffix: '%', good: 'hi' },
  { key: 'calmar', label: 'Calmar', good: 'hi' },
  { key: 'te_vs_bench_pct', label: 'TE vs FTSE', suffix: '%', good: 'lo' },
  { key: 'information_ratio', label: 'Information Ratio', good: 'hi' },
  { key: 'active_share_pct', label: 'Active Share', suffix: '%' },
  { key: 'max_weight_pct', label: 'Max weight 1 mã', suffix: '%', good: 'lo' },
  { key: 'sector_hhi', label: 'Sector HHI', good: 'lo' },
  { key: 'ann_turnover_pct', label: 'Turnover/năm', suffix: '%', good: 'lo' },
  { key: 'worst_roll_6m_pp', label: 'Worst 6M vs FTSE', suffix: 'pp', good: 'hi' },
]

export function MetricCards({ metrics }: { metrics: Metrics }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
      {METRIC_DISPLAY.map(m => (
        <div key={m.key} className="bg-vps-offwhite rounded-vps border border-vps-lavender px-3 py-2">
          <div className="text-[10px] text-vps-purple tracking-vps leading-tight">{m.label}</div>
          <div className="text-sm font-bold text-vps-black">
            {metrics[m.key]}{m.suffix ?? ''}
          </div>
        </div>
      ))}
    </div>
  )
}

// Compare metrics table
export function CompareTable({ strategies }: {
  strategies: { name: string; metrics: Record<string, number | string>; capacity?: { bottleneck_L: number; binding_ticker: string | null } }[]
}) {
  const rows = METRIC_DISPLAY
  return (
    <div className="overflow-x-auto">
      <table className="vps-table text-xs w-full">
        <thead>
          <tr>
            <th>Metric</th>
            {strategies.map(s => <th key={s.name} className="!text-right">{s.name}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map(m => (
            <tr key={m.key}>
              <td className="text-vps-black/80">{m.label}</td>
              {strategies.map(s => (
                <td key={s.name} className="text-right font-medium tabular-nums">
                  {s.metrics[m.key]}{s.metrics[m.key] === '—' ? '' : (m.suffix ?? '')}
                </td>
              ))}
            </tr>
          ))}
          {strategies.some(s => s.capacity) && (
            <>
              <tr className="bg-vps-offwhite">
                <td className="text-vps-black/80">Nút thắt thanh khoản L</td>
                {strategies.map(s => (
                  <td key={s.name} className="text-right font-medium tabular-nums">{s.capacity?.bottleneck_L ?? '—'}</td>
                ))}
              </tr>
              <tr className="bg-vps-offwhite">
                <td className="text-vps-black/80">Mã nghẽn</td>
                {strategies.map(s => (
                  <td key={s.name} className="text-right font-medium">{s.capacity?.binding_ticker ?? '—'}</td>
                ))}
              </tr>
            </>
          )}
        </tbody>
      </table>
    </div>
  )
}

// Download one column of the grid as a `ticker,weight` CSV.
// Zero rows are dropped: what the PM wants is the target book, not the whole basket.
function downloadColumn(grid: WeightGridResult, col: string) {
  const rows = grid.rows
    .map(r => ({ ticker: String(r.ticker), weight: Number(r[col]) }))
    .filter(r => r.weight > 0)
    .sort((a, b) => b.weight - a.weight)
  const csv = ['ticker,weight', ...rows.map(r => `${r.ticker},${r.weight.toFixed(2)}`)].join('\n')
  const stamp = grid.forced ? `forced_${grid.rebalance_date}` : grid.date
  const name = col.replace(/[^A-Za-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '') || 'weights'
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url
  a.download = `weights_${name}_${stamp}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// Fixed-date weight grid
export function WeightGrid({ grid }: { grid: WeightGridResult }) {
  const methods = grid.columns.filter(c => c !== 'FTSE')
  const cell = (v: number, ftse: number, key: string) => {
    const dev = v - ftse
    const bg = dev > 0.5 ? 'bg-vps-green/50 text-vps-black'
      : dev < -0.5 ? 'bg-vps-red/60 text-vps-deep' : 'text-vps-black/80'
    return <td key={key} className={`text-right tabular-nums ${bg}`}>{v.toFixed(1)}</td>
  }
  return (
    <div className="overflow-x-auto">
      <table className="vps-table text-xs w-full">
        <thead>
          <tr>
            <th>Mã</th>
            {grid.columns.map(c => (
              <th key={c} className={`!text-right ${c === 'FTSE' ? '!text-vps-black' : ''}`}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.rows.map(row => (
            <tr key={String(row.ticker)}>
              <td className="font-semibold">{row.ticker}</td>
              {methods.map(m => cell(Number(row[m]), Number(row.FTSE), m))}
              <td className="text-right tabular-nums font-medium text-vps-black">{Number(row.FTSE).toFixed(1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-[10px] text-vps-gray mt-1">Xanh (Growth) = overweight vs FTSE, hồng (Potential) = underweight (ngày {grid.date})</p>
      <div className="flex flex-wrap items-center gap-2 mt-2">
        <span className="text-[10px] text-vps-gray">⬇ CSV (ticker, weight — bỏ mã weight 0):</span>
        {grid.columns.map(c => (
          <button key={c} onClick={() => downloadColumn(grid, c)}
            className="vps-btn-outline !px-2 !py-0.5 !text-[11px]"
            title={`Tải weight của ${c} tại ${grid.forced ? grid.rebalance_date : grid.date}`}>
            {c}
          </button>
        ))}
      </div>
    </div>
  )
}

// Liquidity and capacity (flow stress)
const EVENT_LABEL: Record<string, string> = {
  redeem: 'Rút/Mua', rebalance: 'Rebalance',
}

export function LiquidityPanel({ spec, config }: { spec: StrategySpec | null; config: LabConfig }) {
  const [aum, setAum] = useState(1000)
  const [redeem, setRedeem] = useState(10)
  const [participation, setParticipation] = useState(20)
  const [tab, setTab] = useState<'redeem' | 'rebalance'>('redeem')
  const [liq, setLiq] = useState<LiquidityResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const run = async () => {
    if (!spec) return
    setBusy(true); setErr('')
    try {
      setLiq(await runLiquidity(spec, config, {
        target_aum: aum, redeem_pct: redeem, participation,
      }))
    } catch (e: any) { setErr(e?.response?.data?.detail ?? String(e)) } finally { setBusy(false) }
  }

  const overLimit = liq && redeem > liq.max_redeem_pct
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3 text-xs">
        <label>Tổng AUM (tỷ)<input type="number" value={aum} onChange={e => setAum(+e.target.value)}
          className="vps-input block w-24 mt-0.5" /></label>
        <label title="Dùng chung cho cả RÚT lẫn MUA — mô hình thanh khoản đối xứng (volume mua/bán giới hạn như nhau)">% dòng tiền/ngày<input type="number" value={redeem} onChange={e => setRedeem(+e.target.value)}
          className="vps-input block w-16 mt-0.5" /></label>
        <label>Participation %<input type="number" value={participation} onChange={e => setParticipation(+e.target.value)}
          className="vps-input block w-16 mt-0.5" /></label>
        <button onClick={run} disabled={!spec || busy}
          className="vps-btn-dark">{busy ? '…' : 'Phân tích'}</button>
      </div>
      {err && <p className="text-xs bg-vps-red text-vps-deep rounded px-2 py-1">{err}</p>}
      {liq?.error && (
        <p className="text-xs bg-vps-yellow text-vps-black rounded px-2 py-1">
          Không phân tích được thanh khoản: {liq.error}
        </p>
      )}
      {liq && !liq.error && (
        <>
          <div className={`rounded-vps px-3 py-2 text-sm ${overLimit ? 'bg-vps-red text-vps-deep' : 'bg-vps-green text-vps-black'}`}>
            Tại <b>{liq.target_aum} tỷ</b>, rổ chịu tối đa <b>{liq.max_redeem_pct}%</b> dòng tiền/ngày (rút hoặc mua) trước khi
            mã <b>{liq.binding_ticker}</b> nghẽn.
            {overLimit && <span className="font-semibold"> ⚠ Mức dòng tiền {redeem}% vượt ngưỡng!</span>}
          </div>

          <div>
            <div className="text-[11px] text-vps-gray mb-1">% dòng tiền/ngày hấp thụ được theo AUM (rút hoặc mua)</div>
            <MultiLineChart height={150} dates={liq.capacity_curve.map(c => `${c.aum_bn}`)}
              series={[{ name: '% dòng tiền/ngày', values: liq.capacity_curve.map(c => c.max_redeem_pct), color: COLORS[1] }]} />
          </div>
          <div>
            <div className="flex gap-1 mb-1">
              {(['redeem', 'rebalance'] as const).map(e => (
                <button key={e} onClick={() => setTab(e)}
                  className={`px-2 py-0.5 text-[11px] rounded tracking-vps ${tab === e ? 'bg-vps-violet text-white' : 'bg-vps-lavender text-vps-deep'}`}>{EVENT_LABEL[e]}</button>
              ))}
            </div>
            <EventTable rows={liq.per_event[tab]} kind={tab} date={liq.rebalance_date} />
          </div>

          {liq.lock_flags.length > 0 && (
            <div className="text-xs text-vps-deep bg-vps-red rounded-vps px-3 py-2">
              🔒 Rủi ro lock (sàn không thoát được): {liq.lock_flags.map(f => `${f.ticker} (${f.liq_bn} tỷ)`).join(', ')}
            </div>
          )}
          <p className="text-[10px] text-vps-gray">
            <b>Est Slip%</b> = σ·√(lượng trade ÷ thanh khoản): lệnh càng lớn so với thanh khoản, giá trượt càng nhiều.
            Cột <b>crash</b> = nhân thêm hệ số impact phiên sốc (Được estimate theo Amihud).
            {liq.short_history.length > 0 && ` Mã lịch sử ngắn (kém tin cậy): ${liq.short_history.join(', ')}.`}
          </p>
        </>
      )}
    </div>
  )
}

function EventTable({ rows, kind, date }: {
  rows: LiqEventRow[]; kind?: 'redeem' | 'rebalance'; date?: string | null
}) {
  const isRebal = kind === 'rebalance'
  return (
    <div>
      {isRebal && (
        <div className="text-[11px] text-vps-black/80 mb-1">
          Kỳ rebalance gần nhất: <b>{date ?? '—'}</b>
        </div>
      )}
      <div className="overflow-x-auto max-h-64 overflow-y-auto">
        <table className="vps-table text-[11px] w-full">
          <thead className="sticky top-0 bg-white">
            <tr>
              <th className="text-left py-1 px-1">Mã</th>
              {isRebal && <th className="text-right py-1 px-1">Weight</th>}
              {isRebal && <th className="text-right py-1 px-1">Δ</th>}
              <th className="text-right py-1 px-1">Cần (tỷ)</th>
              <th className="text-right py-1 px-1">Hấp thụ</th>
              <th className="text-right py-1 px-1">Thiếu%</th>
              <th className="text-right py-1 px-1">Phiên</th>
              <th className="text-right py-1 px-1">Est Slip%</th>
              <th className="text-right py-1 px-1">Est Slip%<br/>(crash)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => {
              const bad = r.shortfall_pct > 0 || r.spill_days > 1
              const d = r.delta_pct ?? 0
              return (
                <tr key={r.ticker} className={bad ? 'bg-vps-red/40' : ''}>
                  <td className="py-1 px-1 font-medium">{r.ticker}</td>
                  {isRebal && (
                    <td className="text-right tabular-nums text-vps-gray">
                      {r.weight_prev_pct}% → {r.weight_new_pct}%
                    </td>
                  )}
                  {isRebal && (
                    <td className={`text-right py-1 px-1 tabular-nums font-medium ${d > 0 ? 'text-vps-black font-semibold' : d < 0 ? 'text-vps-deep' : 'text-vps-gray'}`}>
                      {d > 0 ? '+' : ''}{r.delta_pct}%
                    </td>
                  )}
                  <td className="text-right py-1 px-1 tabular-nums">{r.required_bn}</td>
                  <td className="text-right py-1 px-1 tabular-nums">{r.available_bn}</td>
                  <td className="text-right py-1 px-1 tabular-nums">{r.shortfall_pct > 0 ? `${r.shortfall_pct}` : '—'}</td>
                  <td className="text-right py-1 px-1 tabular-nums">{r.spill_days}</td>
                  <td className="text-right py-1 px-1 tabular-nums">{r.slippage_pct}</td>
                  <td className="text-right py-1 px-1 tabular-nums">{r.slippage_crash_pct}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// Feasibility: minimum AUM
export function FeasibilityCard({ f }: { f: Feasibility }) {
  const curve = f.te_curve ?? []
  const cur = curve.find(p => p.is_current)
  return (
    <div>
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Min AUM khả thi" value={`${f.min_aum_bn} tỷ`} />
        <Stat label="AUM khuyến nghị" value={`${f.recommended_aum_bn} tỷ`} />
        <Stat label="Bottleneck (lệch lô)"
          value={f.bottleneck_ticker ? `${f.bottleneck_ticker} · ${f.bottleneck_weight_pct}%` : '—'} />
      </div>
      {curve.length > 0 && (
        <div className="mt-3">
          <div className="text-[11px] text-vps-gray mb-1">
          Tracking error
            {cur && <> · AUM hiện tại <b>{cur.aum_bn} tỷ</b> → TE <b>{cur.te_pct}%</b></>}
          </div>
          <MultiLineChart height={160} yLabel="TE %"
            dates={curve.map(p => String(p.aum_bn))}
            series={[{ name: 'Impl. TE %', values: curve.map(p => p.te_pct), color: '#8229E3' }]} />
          <div className="text-[10px] text-vps-gray mt-0.5">Trục X = AUM (tỷ); TE giảm dần khi vốn lớn hơn.</div>
        </div>
      )}
    </div>
  )
}

// Attribution: contribution to excess return
export function AttributionPanel({ attr }: { attr: AttributionResult }) {
  const sorted = [...attr.rows].sort((a, b) => a.contrib_pp - b.contrib_pp)
  const top = [...sorted.slice(0, 6), ...sorted.slice(-6)]
    .filter((v, i, a) => a.findIndex(x => x.ticker === v.ticker) === i)
  const maxAbs = Math.max(...top.map(r => Math.abs(r.contrib_pp)), 0.01)
  return (
    <div className="space-y-2">
      <div className="text-[11px] text-vps-gray">
        {attr.window_start} → {attr.window_end} · tổng excess <b>{attr.total_contrib_pp}pp</b>
      </div>
      <div className="space-y-0.5">
        {top.map(r => (
          <div key={r.ticker} className="flex items-center gap-2 text-xs">
            <span className="w-10 font-medium">{r.ticker}</span>
            <div className="flex-1 relative h-4 bg-vps-offwhite">
              <div className="absolute top-0 bottom-0 left-1/2 w-px bg-vps-gray" />
              <div className={`absolute top-0.5 bottom-0.5 ${r.contrib_pp < 0 ? 'bg-vps-red' : 'bg-vps-green'}`}
                style={r.contrib_pp < 0
                  ? { right: '50%', width: `${(Math.abs(r.contrib_pp) / maxAbs) * 48}%` }
                  : { left: '50%', width: `${(r.contrib_pp / maxAbs) * 48}%` }} />
            </div>
            <span className="w-14 text-right tabular-nums">{r.contrib_pp}pp</span>
            <span className="w-20 text-right text-vps-gray">Δw {r.wdiff_pct}%</span>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-vps-gray">Hồng = kéo tụt vs FTSE, xanh = đẩy lên (Δw = over/underweight tb)</p>
    </div>
  )
}

function Stat({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className={`rounded-vps border px-3 py-2 ${warn ? 'border-vps-yellow bg-vps-yellow' : 'border-vps-lavender bg-vps-offwhite'}`}>
      <div className="text-[10px] text-vps-purple tracking-vps">{label}</div>
      <div className="text-sm font-bold text-vps-black">{value}</div>
    </div>
  )
}
