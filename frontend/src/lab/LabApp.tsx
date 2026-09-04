import { Fragment, useEffect, useState } from 'react'
import {
  getDefaults, generateStrategy, runBacktest, runCompare, runWeightGrid, runAttribution,
  saveStrategy, listStrategies, deleteStrategy, explainStrategy,
} from './api'
import type {
  Defaults, LabConfig, BacktestResult, CompareResult, WeightGridResult, AttributionResult,
  SavedStrategy, StrategyExplanation,
} from './types'
import {
  MultiLineChart, MetricCards, CompareTable, WeightGrid, LiquidityPanel, FeasibilityCard,
  AttributionPanel, StrategyExplanationBox, VpsLogo, COLORS, CHART_INK, CHART_MUTED,
} from './components'
import { JobsTab } from './JobsTab'
import { WeightsTab } from './WeightsTab'

type Tab = 'build' | 'compare' | 'saved' | 'jobs' | 'weights'
const TAB_LABEL: Record<Tab, string> = {
  build: 'Build & Backtest', compare: 'Compare', saved: 'Saved',
  jobs: 'Operations', weights: 'Benchmark',
}

export default function LabApp() {
  const [defaults, setDefaults] = useState<Defaults | null>(null)
  const [cap, setCap] = useState(25)
  const [startDate, setStartDate] = useState('2020-01-02')
  const [endDate, setEndDate] = useState('')          // hydrated with the last session that has data
  const [adtvFloor, setAdtvFloor] = useState('')
  const [maxNames, setMaxNames] = useState('')
  const [excluded, setExcluded] = useState<string[]>([])
  const [nl, setNl] = useState('')
  const [code, setCode] = useState('')
  const [tab, setTab] = useState<Tab>('build')

  const [bootErr, setBootErr] = useState('')

  useEffect(() => {
    getDefaults().then(d => {
      setDefaults(d); setCap(Math.round(d.default_cap * 100))
      if (d.start_date) setStartDate(d.start_date)
      setEndDate(d.end_date ?? '')
    }).catch((e: any) => setBootErr(e?.response?.data?.detail ?? String(e)))
  }, [])

  const universe = defaults
    ? defaults.universe.map(s => s.ticker).filter(t => !excluded.includes(t))
    : undefined

  const config: LabConfig = {
    start_date: startDate, end_date: endDate || null, cap: cap / 100,
    adtv_floor_bn: adtvFloor ? +adtvFloor : null,
    max_names: maxNames ? +maxNames : null,
    universe,
  }

  const loadStrategy = (s: SavedStrategy) => { setNl(s.nl_prompt); setCode(s.code); setTab('build') }

  return (
    <div className="min-h-screen bg-vps-offwhite">
      {/* Violet band: the brand colour must cover a large share of the surface */}
      <header className="bg-vps-violet text-white">
        <div className="max-w-7xl mx-auto px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <VpsLogo />
            <div className="border-l border-white/30 pl-4">
              <h1 className="text-lg font-bold tracking-vps leading-tight">Portfolio Construction</h1>
            </div>
          </div>
          <span className="vps-chip bg-white/15 text-white border border-white/30">Internal Tool</span>
        </div>
        <nav className="max-w-7xl mx-auto px-8 flex gap-1">
          {(Object.keys(TAB_LABEL) as Tab[]).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium tracking-vps rounded-t-vps transition-colors ${
                tab === t ? 'bg-vps-offwhite text-vps-violet' : 'text-white/85 hover:bg-white/10'}`}>
              {TAB_LABEL[t]}
            </button>
          ))}
        </nav>
      </header>

      <main className="max-w-7xl mx-auto px-8 py-6 space-y-4">
        {bootErr && (
          <div className="vps-card p-4 border-l-4 !border-l-vps-violet bg-vps-red/60">
            <div className="text-sm font-semibold text-vps-deep">Không tải được cấu hình từ API</div>
            <p className="text-xs text-vps-deep/90 mt-1">{bootErr}</p>
            <p className="text-xs text-vps-deep/90">Kiểm tra container <b>api</b> đang chạy và nginx proxy được /api.</p>
          </div>
        )}
        {defaults && !defaults.data_ready && (
          <div className="vps-card p-4 border-l-4 !border-l-vps-violet bg-vps-yellow/60">
            <div className="text-sm font-semibold text-vps-black">Chưa có dữ liệu thị trường</div>
            <p className="text-xs text-vps-black/80 mt-1">
              Snapshot giá còn rỗng nên chưa backtest được. Mở tab <b>Operations</b> → kiểm tra kết
              nối Data Platform → bấm <b>⟳ Tải lại toàn bộ lịch sử</b> để kéo dữ liệu về lần đầu.
            </p>
          </div>
        )}
        {tab !== 'jobs' && tab !== 'weights' && (
          <>
            <ConfigBar defaults={defaults} cap={cap} setCap={setCap} startDate={startDate}
              setStartDate={setStartDate} endDate={endDate} setEndDate={setEndDate}
              adtvFloor={adtvFloor} setAdtvFloor={setAdtvFloor} maxNames={maxNames} setMaxNames={setMaxNames} />
            <UniversePanel universe={defaults?.universe ?? []} excluded={excluded} setExcluded={setExcluded} />
          </>
        )}

        {tab === 'build' && <BuildTab config={config} defaults={defaults} nl={nl} setNl={setNl} code={code} setCode={setCode} />}
        {tab === 'compare' && <CompareTab config={config} defaults={defaults} />}
        {tab === 'saved' && <SavedTab onLoad={loadStrategy} config={config} />}
        {tab === 'jobs' && <JobsTab />}
        {tab === 'weights' && <WeightsTab />}

        <footer className="text-[10px] text-vps-gray pt-4 tracking-vps">
          Metrics GROSS — chưa trừ phí/thuế/trượt giá. Dữ liệu từ Data Platform nội bộ.
        </footer>
      </main>
    </div>
  )
}

// Universe selector: exclude sectors or tickers
function UniversePanel({ universe, excluded, setExcluded }: {
  universe: { ticker: string; name: string; sector: string }[]
  excluded: string[]; setExcluded: (s: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const sectors = [...new Set(universe.map(s => s.sector))]
  const included = universe.filter(s => !excluded.includes(s.ticker)).length
  const toggle = (t: string) =>
    setExcluded(excluded.includes(t) ? excluded.filter(x => x !== t) : [...excluded, t])
  const toggleSector = (sec: string) => {
    const ticks = universe.filter(s => s.sector === sec).map(s => s.ticker)
    const allExcluded = ticks.every(t => excluded.includes(t))
    setExcluded(allExcluded ? excluded.filter(t => !ticks.includes(t)) : [...new Set([...excluded, ...ticks])])
  }

  return (
    <div className="vps-card p-4">
      <button onClick={() => setOpen(o => !o)} className="flex items-center gap-2 text-sm font-medium text-vps-black">
        <span className="text-vps-violet">{open ? '▾' : '▸'}</span> Rổ cổ phiếu: <b>{included}/{universe.length}</b> mã
        {excluded.length > 0 && <span className="vps-chip bg-vps-yellow text-vps-black">loại {excluded.length}</span>}
      </button>
      {open && (
        <div className="mt-3 grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3">
          {sectors.map(sec => {
            const ticks = universe.filter(s => s.sector === sec)
            const allExcluded = ticks.every(s => excluded.includes(s.ticker))
            return (
              <div key={sec}>
                <label className="flex items-center gap-1.5 text-xs font-semibold text-vps-deep mb-1">
                  <input type="checkbox" checked={!allExcluded} onChange={() => toggleSector(sec)} />
                  {sec}
                </label>
                <div className="flex flex-wrap gap-1 pl-4">
                  {ticks.map(s => {
                    const inc = !excluded.includes(s.ticker)
                    return (
                      <button key={s.ticker} onClick={() => toggle(s.ticker)} title={s.name}
                        className={`px-1.5 py-0.5 text-[11px] rounded border tracking-vps ${inc
                          ? 'bg-vps-lavender border-vps-lavender text-vps-deep'
                          : 'bg-white border-vps-offwhite text-vps-gray line-through'}`}>
                        {s.ticker}
                      </button>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// Saved strategies
function SavedTab({ onLoad, config }: { onLoad: (s: SavedStrategy) => void; config: LabConfig }) {
  const [items, setItems] = useState<SavedStrategy[]>([])
  const [err, setErr] = useState('')
  const [openId, setOpenId] = useState<number | null>(null)
  const [expl, setExpl] = useState<Record<number, StrategyExplanation | null>>({})
  const [explBusy, setExplBusy] = useState<number | null>(null)
  const refresh = () => listStrategies().then(setItems).catch(e => setErr(String(e)))
  useEffect(() => { refresh() }, [])

  const del = async (id: number) => {
    await deleteStrategy(id); refresh()
  }

  const toggleExpl = (s: SavedStrategy) => {
    if (openId === s.id) { setOpenId(null); return }
    setOpenId(s.id)
    if (expl[s.id] === undefined) {
      setExplBusy(s.id)
      explainStrategy({ code: s.code }, config)
        .then(e => setExpl(p => ({ ...p, [s.id]: e })))
        .catch(() => setExpl(p => ({ ...p, [s.id]: null })))
        .finally(() => setExplBusy(null))
    }
  }

  return (
    <div className="vps-card p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-semibold text-vps-black tracking-vps">Chiến lược đã lưu (portfolio gốc)</span>
        <button onClick={refresh} className="vps-btn-ghost text-xs py-1">↻ Tải lại</button>
      </div>
      {err && <p className="text-xs text-vps-deep bg-vps-red rounded px-2 py-1">{err}</p>}
      {items.length === 0 ? <p className="text-sm text-vps-gray">Chưa có chiến lược nào được lưu.</p> : (
        <table className="vps-table text-xs w-full">
          <thead>
            <tr>
              <th>Tên</th>
              <th className="!text-right">Final</th>
              <th className="!text-right">Sharpe</th>
              <th className="!text-right">TE%</th>
              <th className="!text-right" title="Sharpe từ lần chạy lại gần nhất (job hàng ngày)">Sharpe mới</th>
              <th>Rebalance</th>
              <th>Lưu lúc</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map(s => (
              <Fragment key={s.id}>
              <tr>
                <td className="font-medium max-w-[220px] truncate" title={s.nl_prompt}>{s.name}</td>
                <td className="text-right tabular-nums">{s.metrics?.final ?? '—'}</td>
                <td className="text-right tabular-nums">{s.metrics?.sharpe ?? '—'}</td>
                <td className="text-right tabular-nums">{s.metrics?.te_vs_bench_pct ?? '—'}</td>
                <td className="text-right tabular-nums" title={s.latest ? `data tới ${s.latest.data_end}` : 'chưa chạy job hàng ngày'}>
                  {s.latest?.error ? <span className="text-vps-deep">⚠</span> : (s.latest?.metrics?.sharpe ?? '—')}
                </td>
                <td>{s.rebalance_schedule}</td>
                <td className="text-vps-gray">{s.created_at?.slice(0, 10)}</td>
                <td className="text-right whitespace-nowrap">
                  <button onClick={() => toggleExpl(s)} className="vps-btn-outline text-[11px] py-0.5 px-2 mr-1">
                    {openId === s.id ? '▲ Giải thích' : '▼ Giải thích'}
                  </button>
                  <button onClick={() => onLoad(s)} className="vps-btn-primary text-[11px] py-0.5 px-2 mr-1">Load</button>
                  <button onClick={() => del(s.id)} className="vps-btn text-[11px] py-0.5 px-2 border border-vps-gray text-vps-deep hover:bg-vps-red">Xóa</button>
                </td>
              </tr>
              {openId === s.id && (
                <tr key={`${s.id}-expl`}>
                  <td colSpan={8} className="pb-3">
                    <StrategyExplanationBox explanation={expl[s.id] ?? null} loading={explBusy === s.id} />
                  </td>
                </tr>
              )}
            </Fragment>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

// Config bar
function ConfigBar({ defaults, cap, setCap, startDate, setStartDate, endDate, setEndDate,
  adtvFloor, setAdtvFloor, maxNames, setMaxNames }: {
  defaults: Defaults | null; cap: number; setCap: (n: number) => void
  startDate: string; setStartDate: (s: string) => void
  endDate: string; setEndDate: (s: string) => void
  adtvFloor: string; setAdtvFloor: (s: string) => void; maxNames: string; setMaxNames: (s: string) => void
}) {
  const fmt = (d?: string | null) => (d ? d.split('-').reverse().join('/') : '—')
  return (
    <div className="vps-card p-4 flex flex-wrap items-end gap-6 border-l-4 !border-l-vps-violet">
      <div>
        <label className="vps-label block mb-1">Rổ cổ phiếu</label>
        <div className="text-sm font-medium">{defaults?.universe.length ?? '—'} mã</div>
      </div>
      <div>
        <label className="vps-label block mb-1">Cap/mã: <b className="text-vps-violet">{cap}%</b></label>
        <input type="range" min={5} max={100} value={cap} onChange={e => setCap(+e.target.value)} className="w-40" />
      </div>
      <div>
        <label className="vps-label block mb-1">Start date</label>
        <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
          min={defaults?.min_date ?? undefined} max={endDate || defaults?.max_date || undefined}
          className="vps-input"
          title={`Ngày bắt đầu backtest — chiến lược phân bổ ngay từ ngày này (sớm nhất ${fmt(defaults?.min_date)})`} />
      </div>
      <div>
        <label className="vps-label block mb-1">End date</label>
        <div className="flex items-center gap-1">
          <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
            min={startDate} max={defaults?.max_date ?? undefined}
            className="vps-input"
            title={`Ngày kết thúc backtest (tính cả ngày này). Mặc định = phiên cuối có data (${fmt(defaults?.max_date)})`} />
          {defaults?.max_date && endDate !== defaults.max_date && (
            <button onClick={() => setEndDate(defaults.max_date!)} title="Về phiên cuối có data"
              className="text-vps-gray hover:text-vps-violet text-sm px-1 leading-none">↺</button>
          )}
        </div>
      </div>
      <div>
        <label className="vps-label block mb-1">ADTV floor (tỷ)</label>
        <input type="number" value={adtvFloor} onChange={e => setAdtvFloor(e.target.value)}
          placeholder="—" className="vps-input w-20" />
      </div>
      <div>
        <label className="vps-label block mb-1">Max số mã</label>
        <input type="number" value={maxNames} onChange={e => setMaxNames(e.target.value)}
          placeholder="—" className="vps-input w-20" />
      </div>
      <div className="text-[11px] text-vps-gray">
        Data: {defaults?.features.join(', ')} <span className="text-vps-lavender">(fundamental/technical...)</span>
      </div>
    </div>
  )
}

// Build tab
function BuildTab({ config, defaults, nl, setNl, code, setCode }: {
  config: LabConfig; defaults: Defaults | null
  nl: string; setNl: (s: string) => void; code: string; setCode: (s: string) => void
}) {
  const [busy, setBusy] = useState<string | null>(null)
  const [bt, setBt] = useState<BacktestResult | null>(null)
  const [attr, setAttr] = useState<AttributionResult | null>(null)
  const [lastSpec, setLastSpec] = useState<{ code?: string; preset?: string } | null>(null)
  // Snapshot of the code and config THAT RAN: Save must use exactly this pair, and if
  // the code or config changes afterwards the displayed result no longer matches.
  const [ranWith, setRanWith] = useState<{ code: string; config: string } | null>(null)
  const [sourcePreset, setSourcePreset] = useState<string | null>(null)
  const [explanation, setExplanation] = useState<StrategyExplanation | null>(null)
  const [explaining, setExplaining] = useState(false)
  const [err, setErr] = useState('')

  const wrap = async (label: string, fn: () => Promise<void>) => {
    setBusy(label); setErr('')
    try { await fn() } catch (e: any) { setErr(e?.response?.data?.detail ?? String(e)) } finally { setBusy(null) }
  }

  const gen = () => wrap('gen', async () => {
    setSourcePreset(null)
    setCode((await generateStrategy(nl, config)).code)
  })
  const run = (spec: { code?: string; preset?: string }) => wrap('run', async () => {
    setAttr(null); setLastSpec(spec); setExplanation(null)
    const cfgSnapshot = JSON.stringify(config)
    setBt(await runBacktest(spec, config))
    setRanWith({ code: spec.code ?? '', config: cfgSnapshot })
    // Explain the strategy just backtested, without blocking the result
    setExplaining(true)
    explainStrategy(spec, config)
      .then(setExplanation).catch(() => setExplanation(null)).finally(() => setExplaining(false))
  })
  // Presets run through the {code} path so the code shows in the textarea and can be edited
  const runPreset = (p: string) => {
    const presetCode = defaults?.preset_code?.[p]
    if (!presetCode) { setErr(`Không có code cho preset ${p}`); return }
    setCode(presetCode)
    setSourcePreset(p)
    run({ code: presetCode })
  }
  const doAttr = () => wrap('attr', async () => {
    if (lastSpec) setAttr(await runAttribution(lastSpec, config))
  })
  const save = () => wrap('save', async () => {
    if (!bt || !ranWith) return
    const name = nl.slice(0, 60) || (sourcePreset ? `${sourcePreset} (tinh chỉnh)` : 'strategy')
    await saveStrategy({ name, nl_prompt: nl, code: ranWith.code,
      config: JSON.parse(ranWith.config), metrics: bt.metrics,
      rebalance_schedule: bt.rebalance_schedule, move_policy: bt.move_policy })
    setErr('✓ Đã lưu portfolio')
  })

  // Does the displayed result still belong to the current code and config?
  const stale = !!bt && (!ranWith || ranWith.code !== code || ranWith.config !== JSON.stringify(config))

  return (
    <div className="grid lg:grid-cols-5 gap-4">
      <div className="lg:col-span-2 vps-card p-4 space-y-3">
        <div>
          <label className="vps-label">Mô tả chiến lược</label>
          <textarea value={nl} onChange={e => setNl(e.target.value)} rows={3}
            placeholder="vd: Equal risk contribution, cap 20%, rebalance quý, no-trade band 1.5%; rebalance thêm khi regime shift (frob_z > 2)"
            className="vps-input w-full mt-1 rounded-vps p-2" />
          <button onClick={gen} disabled={!nl || !!busy} className="vps-btn-primary mt-2">
            {busy === 'gen' ? 'Đang sinh code…' : 'Generate'}
          </button>
          <span className="ml-2 text-[11px] text-vps-gray">hoặc preset:</span>
          <div className="flex flex-wrap gap-1 mt-1.5">
            {defaults?.presets.map(p => (
              <button key={p} onClick={() => runPreset(p)} disabled={!!busy}
                className="px-2 py-0.5 text-[11px] rounded bg-vps-lavender text-vps-deep hover:bg-vps-lilac disabled:opacity-40 tracking-vps">{p}</button>
            ))}
          </div>
        </div>
        <div>
          <label className="vps-label">Code chiến lược</label>
          <textarea value={code} onChange={e => setCode(e.target.value)} rows={14}
            spellCheck={false}
            className="w-full mt-1 text-xs font-mono border border-vps-gray rounded-vps p-2 bg-vps-offwhite focus:outline-none focus:border-vps-violet" />
          <div className="flex gap-2 mt-2">
            <button onClick={() => run({ code })} disabled={!code || !!busy} className="vps-btn-dark">
              {busy === 'run' ? 'Đang backtest…' : '▶ Backtest'}
            </button>
            <button onClick={save} disabled={!bt || !code || !!busy || stale} className="vps-btn-outline"
              title={stale ? 'Code hoặc cấu hình đã đổi sau lần chạy — backtest lại trước khi lưu'
                           : 'Lưu đúng code + cấu hình của lần backtest đang hiển thị'}>
              Save portfolio
            </button>
          </div>
          {stale && (
            <p className="text-[11px] text-vps-deep bg-vps-yellow rounded px-2 py-1 mt-1">
              ⚠ Code/cấu hình đã thay đổi — kết quả bên phải là của lần chạy trước. Backtest lại để lưu.
            </p>
          )}
        </div>
        {(explanation || explaining) && (
          <div>
            <div className="vps-label mb-1">Giải thích chiến lược (công thức → ý nghĩa)</div>
            <StrategyExplanationBox explanation={explanation} loading={explaining} />
          </div>
        )}
        {err && (
          <p className={`text-xs rounded px-2 py-1 ${err.startsWith('✓') ? 'bg-vps-green text-vps-black' : 'bg-vps-red text-vps-deep'}`}>{err}</p>
        )}
      </div>

      <div className="lg:col-span-3 vps-card p-4 space-y-4">
        {!bt ? <p className="text-sm text-vps-gray">Backtest để xem kết quả vs FTSE.</p> : (
          <>
            <div>
              <div className="text-xs text-vps-gray mb-1">
                Rebalance: <b className="text-vps-deep">{bt.rebalance_schedule}</b> · move: <b className="text-vps-deep">{bt.move_policy}</b>
              </div>
              <MetricCards metrics={bt.metrics} />
            </div>
            {bt.warnings.length > 0 && (
              <div className="text-xs text-vps-black bg-vps-yellow rounded-vps px-3 py-2 space-y-0.5">
                {bt.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
              </div>
            )}
            <div>
              <div className="vps-label mb-1">Feasibility (lot rounding)</div>
              <FeasibilityCard f={bt.feasibility} />
            </div>
            <div>
              <div className="vps-label mb-1">Cumulative return vs FTSE & VNINDEX (base 100)</div>
              <MultiLineChart dates={bt.dates} series={[
                { name: 'Strategy', values: bt.port_cum, color: COLORS[0] },
                { name: 'FTSE', values: bt.bench_cum, color: CHART_INK },
                { name: 'VNINDEX', values: bt.vnindex_cum, color: CHART_MUTED, dashed: true },
              ]} />
            </div>
            <div>
              <div className="vps-label mb-1">Max weight 1 mã theo thời gian</div>
              <MultiLineChart height={160} dates={bt.dates}
                series={[{ name: 'max weight %', values: bt.max_weight_series, color: COLORS[1] }]}
                refLine={config.cap ? config.cap * 100 : undefined} />
            </div>
            {bt.exposure_series && (
              <div>
                <div className="vps-label mb-1">% tiền mặt theo thời gian (regime overlay)</div>
                <MultiLineChart height={160} dates={bt.dates} yLabel="cash %"
                  series={[{ name: 'cash %', values: bt.exposure_series.map(e => +(100 - e).toFixed(1)), color: COLORS[2] }]} />
              </div>
            )}
            <div className="border-t border-vps-lavender pt-3">
              <div className="vps-label mb-2">Liquidity &amp; Capacity (rủi ro thanh khoản theo AUM)</div>
              <LiquidityPanel spec={lastSpec} config={config} />
            </div>
            <div className="border-t border-vps-lavender pt-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="vps-label">Attribution vs FTSE (6 tháng cuối)</span>
                <button onClick={doAttr} disabled={!!busy || !lastSpec}
                  className="vps-btn-ghost text-xs py-0.5 px-2">{busy === 'attr' ? '…' : 'Chạy'}</button>
              </div>
              {attr && <AttributionPanel attr={attr} />}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// Compare tab
function CompareTab({ config, defaults }: { config: LabConfig; defaults: Defaults | null }) {
  const [sel, setSel] = useState<string[]>([])
  const [idxSel, setIdxSel] = useState<string[]>(['FTSE', 'VNINDEX'])  // both indices on by default
  const [saved, setSaved] = useState<SavedStrategy[]>([])
  const [savedSel, setSavedSel] = useState<number[]>([])
  const [cmp, setCmp] = useState<CompareResult | null>(null)
  const [grid, setGrid] = useState<WeightGridResult | null>(null)
  const [gridDate, setGridDate] = useState('')
  const [forceRebal, setForceRebal] = useState(false)
  // Force only applies at the last session, so lock the date field to end_date.
  const endDate = config.end_date || defaults?.max_date || ''
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => { listStrategies().then(setSaved).catch(() => {}) }, [])

  const toggle = (p: string) => setSel(s => s.includes(p) ? s.filter(x => x !== p) : [...s, p])
  const toggleIdx = (n: string) => setIdxSel(s => s.includes(n) ? s.filter(x => x !== n) : [...s, n])
  const toggleSaved = (id: number) =>
    setSavedSel(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id])

  const strategies = [
    ...sel.map(p => ({ name: p, spec: { preset: p } as const })),
    ...savedSel.map(id => {
      const s = saved.find(x => x.id === id)!
      return { name: `${s.name || 'strategy'} #${s.id}`, spec: { code: s.code } }
    }),
  ]

  const run = async () => {
    setBusy(true); setErr('')
    try {
      const [c, g] = await Promise.all([
        runCompare(strategies, config),
        runWeightGrid(strategies, config,
          forceRebal ? undefined : (gridDate || undefined), forceRebal),
      ])
      setCmp(c); setGrid(g)
    } catch (e: any) { setErr(e?.response?.data?.detail ?? String(e)) } finally { setBusy(false) }
  }

  return (
    <div className="space-y-4">
      <div className="vps-card p-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="vps-label">Preset:</span>
          {defaults?.presets.map(p => (
            <label key={p} className="flex items-center gap-1 text-sm">
              <input type="checkbox" checked={sel.includes(p)} onChange={() => toggle(p)} />{p}
            </label>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-3 mt-2 pt-2 border-t border-vps-lavender">
          <span className="vps-label">Chỉ số:</span>
          {(['FTSE', 'VNINDEX'] as const).map(n => (
            <label key={n} className="flex items-center gap-1 text-sm">
              <input type="checkbox" checked={idxSel.includes(n)} onChange={() => toggleIdx(n)} />{n}
            </label>
          ))}
          <label className="flex items-center gap-1 text-sm ml-auto"
            title="Ép rebalance tại phiên dữ liệu cuối → grid hiện weight SAU rebalance (danh mục mục tiêu nếu đặt lệnh phiên tới), thay vì weight đang nắm đã trôi giá.">
            <input type="checkbox" checked={forceRebal}
              onChange={e => setForceRebal(e.target.checked)} />
            Force rebalance
          </label>
          <span className="text-xs text-vps-gray">Weight grid ngày:</span>
          <input type="date" value={forceRebal ? endDate : gridDate} disabled={forceRebal}
            onChange={e => setGridDate(e.target.value)}
            min={config.start_date} max={endDate}
            className="vps-input text-xs disabled:bg-vps-offwhite disabled:text-vps-gray"
            placeholder="cuối kỳ"
            title="Ngày chốt weight để so sánh — trong khoảng backtest. Để trống = phiên cuối." />
          <button onClick={run} disabled={busy || strategies.length === 0} className="vps-btn-primary">
            {busy ? 'Đang chạy…' : '▶ So sánh'}
          </button>
        </div>
        {saved.length > 0 && (
          <div className="flex flex-wrap items-center gap-3 mt-2 pt-2 border-t border-vps-lavender">
            <span className="vps-label">💾 Đã lưu:</span>
            {saved.map(s => (
              <label key={s.id} className="flex items-center gap-1 text-sm" title={s.nl_prompt}>
                <input type="checkbox" checked={savedSel.includes(s.id)} onChange={() => toggleSaved(s.id)} />
                {s.name || `strategy #${s.id}`}
              </label>
            ))}
          </div>
        )}
        {err && <p className="text-xs bg-vps-red text-vps-deep rounded px-2 py-1 mt-2">{err}</p>}
      </div>

      {cmp && (
        <div className="grid lg:grid-cols-2 gap-4">
          <div className="vps-card p-4">
            <div className="vps-label mb-2">Cumulative return</div>
            <MultiLineChart dates={cmp.dates} series={[
              ...cmp.strategies.map((s, i) => ({ name: s.name, values: s.port_cum, color: COLORS[i % COLORS.length] })),
              ...(idxSel.includes('FTSE') ? [{ name: 'FTSE', values: cmp.bench_cum, color: CHART_INK, dashed: true }] : []),
              ...(idxSel.includes('VNINDEX') ? [{ name: 'VNINDEX', values: cmp.vnindex_cum, color: CHART_MUTED, dashed: true }] : []),
            ]} />
            {cmp.strategies.some(s => s.exposure_series) && (
              <>
                <div className="vps-label mt-3 mb-1">
                  % tiền mặt theo thời gian
                  <span className="font-normal normal-case text-vps-gray"> — chiến lược không có regime overlay luôn full cổ phiếu (0% cash)</span>
                </div>
                <MultiLineChart height={160} dates={cmp.dates} yLabel="cash %" series={
                  cmp.strategies.map((s, i) => ({
                    name: s.name,
                    values: s.exposure_series
                      ? s.exposure_series.map(e => +(100 - e).toFixed(1))
                      : cmp.dates.map(() => 0),
                    color: COLORS[i % COLORS.length],
                  }))
                } />
              </>
            )}
            <div className="vps-label mt-3 mb-2">Metrics</div>
            <CompareTable strategies={[
              ...cmp.strategies,
              ...(idxSel.includes('FTSE') && cmp.bench_metrics ? [{ name: 'FTSE', metrics: cmp.bench_metrics }] : []),
              ...(idxSel.includes('VNINDEX') && cmp.vnindex_metrics ? [{ name: 'VNINDEX', metrics: cmp.vnindex_metrics }] : []),
            ]} />
          </div>
          <div className="vps-card p-4">
            <div className="vps-label mb-2">
              {grid?.forced
                ? `Weight SAU khi ép rebalance ${grid.rebalance_date} (chốt data ${grid.date}, vs FTSE)`
                : 'Weight từng cổ theo phương pháp (vs FTSE)'}
            </div>
            {grid && <WeightGrid grid={grid} />}
          </div>
        </div>
      )}
    </div>
  )
}
