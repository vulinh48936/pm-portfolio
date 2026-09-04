import { useEffect, useRef, useState } from 'react'
import { getJobsStatus, getJobsResults, runJob, pingMarketApi, getSchedule, saveSchedule } from './api'
import type { JobsStatus, JobsResults, DailyRun } from './types'
import { StatusDot } from './components'

const STATUS_STYLE: Record<string, string> = {
  ok: 'bg-vps-green text-vps-black',
  partial: 'bg-vps-yellow text-vps-black',
  failed: 'bg-vps-red text-vps-deep',
  running: 'bg-vps-lavender text-vps-deep',
}

const fmtTs = (s?: string | null) => (s ? s.replace('T', ' ').slice(0, 19) : '—')
const dayLabel = (d?: string) => (d === 'T-1' ? 'phiên hôm trước (T-1)' : 'phiên hôm nay (T)')

/** Operations tab: editable schedule, data sync, and the daily backtest results. */
export function JobsTab() {
  const [st, setSt] = useState<JobsStatus | null>(null)
  const [res, setRes] = useState<JobsResults | null>(null)
  const [runId, setRunId] = useState<number | undefined>(undefined)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [kind, setKind] = useState<'all' | 'preset' | 'saved'>('all')
  const [sync, setSync] = useState(true)

  // The interval calls `refresh`, so it must read the CURRENT runId through a ref;
  // a closure variable would make polling jump back to the newest run.
  const runIdRef = useRef<number | undefined>(undefined)
  runIdRef.current = runId

  const refresh = async () => {
    try {
      const [s, r] = await Promise.all([getJobsStatus(), getJobsResults(runIdRef.current)])
      setSt(s); setRes(r)
    } catch (e: any) { setMsg(e?.response?.data?.detail ?? String(e)) }
  }
  useEffect(() => { refresh() }, [runId])
  useEffect(() => {                                   // poll every 5s while a job runs
    if (!st?.running) return
    const id = setInterval(refresh, 5000)
    return () => clearInterval(id)
  }, [st?.running])

  const trigger = async (fullSync = false) => {
    if (fullSync && !confirm(
      'Tải lại TOÀN BỘ lịch sử giá từ Data Platform (ghi đè snapshot hiện có)?\n\n' +
      'Dùng khi có cổ tức/chia tách làm đổi cả chuỗi giá điều chỉnh. Mất vài phút và ' +
      'cắt dữ liệu cũ hơn MARKET_HISTORY_START.')) return
    setBusy(true); setMsg('')
    try {
      await runJob({ sync: fullSync ? true : sync, full_sync: fullSync })
      setMsg(fullSync ? '▶ Đang tải lại toàn bộ lịch sử (chạy nền)' : '▶ Job đã khởi động (chạy nền)')
      setTimeout(refresh, 1500)
    } catch (e: any) { setMsg(e?.response?.data?.detail ?? String(e)) }
    finally { setBusy(false) }
  }
  const ping = async () => {
    setBusy(true)
    try { const p = await pingMarketApi(); setMsg(p.ok ? `✓ ${p.detail}` : `✗ ${p.detail}`) }
    finally { setBusy(false) }
  }

  const rows = (res?.results ?? []).filter(r => kind === 'all' || r.kind === kind)
  const dataDay = st?.scheduler.data_day

  return (
    <div className="space-y-4">
      {/* System status */}
      <div className="grid md:grid-cols-4 gap-3">
        <ScheduleCard st={st} onSaved={refresh} />
        <Card title="Data Platform (CCP + API)">
          <div className="flex items-center gap-2"><StatusDot ok={!!st?.market_api.configured} />
            <span className="text-sm font-medium">{st?.market_api.configured ? 'Đã cấu hình' : 'Thiếu CCP_URL / MARKET_API_URL'}</span></div>
          <div className="text-[11px] text-vps-gray mt-1 truncate" title={st?.market_api.ccp_url ?? ''}>CCP: {st?.market_api.ccp_url ?? '—'}</div>
          <div className="text-[11px] text-vps-gray truncate" title={st?.market_api.url ?? ''}>Data: {st?.market_api.url ?? '—'}</div>
          <button onClick={ping} disabled={busy || !st?.market_api.configured}
            className="vps-btn-ghost text-[11px] py-0.5 px-2 mt-1">Kiểm tra kết nối</button>
        </Card>
        <Card title="LLM nội bộ">
          <div className="flex items-center gap-2"><StatusDot ok={!!st?.llm.ok} />
            <span className="text-sm font-medium">{st?.llm.ok ? 'Kết nối OK' : 'Không kết nối'}</span></div>
          <div className="text-[11px] text-vps-gray mt-1 truncate" title={st?.llm.base_url ?? ''}>{st?.llm.model ?? '—'} @ {st?.llm.base_url ?? '—'}</div>
          {st?.llm.detail && <div className="text-[11px] text-vps-deep truncate" title={st.llm.detail}>{st.llm.detail}</div>}
        </Card>
        <Card title="Vùng dữ liệu">
          <div className="text-sm font-medium">Giá: {st?.data.price_start} → <b className="text-vps-violet">{st?.data.price_end}</b></div>
          <div className="text-xs text-vps-gray mt-1">Index FTSE: {st?.data.index_start} → {st?.data.index_end}</div>
        </Card>
      </div>

      {/* Manual trigger */}
      <div className="vps-card p-4 flex flex-wrap items-center gap-3 border-l-4 !border-l-vps-violet">
        <label className="flex items-center gap-1.5 text-sm"
          title="Bỏ tick nếu chỉ muốn backtest lại trên dữ liệu đang có, không gọi Data Platform.">
          <input type="checkbox" checked={sync} onChange={e => setSync(e.target.checked)} />
          Đồng bộ dữ liệu tới <b>{dayLabel(dataDay)}</b> trước khi backtest
        </label>
        <button onClick={() => trigger(false)} disabled={busy || !!st?.running} className="vps-btn-primary">
          {st?.running ? '⏳ Job đang chạy…' : '▶ Chạy job ngay'}
        </button>
        <button onClick={() => trigger(true)} disabled={busy || !!st?.running}
          title="Crawl lại toàn bộ lịch sử — dùng sau cổ tức/chia tách vì giá điều chỉnh của cả chuỗi quá khứ thay đổi."
          className="vps-btn-outline text-xs">⟳ Tải lại toàn bộ lịch sử</button>
        <button onClick={refresh} className="vps-btn-ghost text-xs">↻ Làm mới</button>
        {msg && <span className="text-xs text-vps-deep">{msg}</span>}
        <span className="ml-auto text-[11px] text-vps-gray">
          Job = lấy token CCP → sync OHLCV → dựng index FTSE/VNINDEX → xóa cache → backtest lại preset + saved
        </span>
      </div>

      {/* Run history and results */}
      <div className="grid lg:grid-cols-3 gap-4">
        <div className="vps-card p-4">
          <div className="vps-label mb-2">Lịch sử chạy</div>
          <table className="vps-table text-xs w-full">
            <thead><tr><th>#</th><th>Bắt đầu</th><th>Data</th><th>Trạng thái</th></tr></thead>
            <tbody>
              {(st?.runs ?? []).map(r => (
                <tr key={r.id} onClick={() => setRunId(r.id)}
                  className={`cursor-pointer hover:bg-vps-offwhite ${res?.run?.id === r.id ? 'bg-vps-lavender/50' : ''}`}>
                  <td className="tabular-nums">{r.id}</td>
                  <td className="tabular-nums">{fmtTs(r.started_at)}<div className="text-[10px] text-vps-gray">{r.trigger}</div></td>
                  <td className="tabular-nums">{r.data_end || '—'}</td>
                  <td><span className={`vps-chip ${STATUS_STYLE[r.status] ?? ''}`}>{r.status}</span></td>
                </tr>
              ))}
              {!st?.runs?.length && <tr><td colSpan={4} className="text-vps-gray">Chưa có lần chạy nào.</td></tr>}
            </tbody>
          </table>
          {res?.run && <RunSummary run={res.run} />}
        </div>

        <div className="vps-card p-4 lg:col-span-2">
          <div className="flex items-center gap-2 mb-2">
            <span className="vps-label">Kết quả backtest {res?.run ? `— run #${res.run.id} (data tới ${res.run.data_end})` : ''}</span>
            <div className="ml-auto flex gap-1">
              {(['all', 'preset', 'saved'] as const).map(k => (
                <button key={k} onClick={() => setKind(k)}
                  className={`px-2 py-0.5 text-[11px] rounded tracking-vps ${kind === k ? 'bg-vps-violet text-white' : 'bg-vps-lavender text-vps-deep'}`}>
                  {k === 'all' ? 'Tất cả' : k}
                </button>
              ))}
            </div>
          </div>
          <div className="overflow-x-auto max-h-[520px] overflow-y-auto">
            <table className="vps-table text-xs w-full">
              <thead className="sticky top-0 bg-white">
                <tr>
                  <th>Chiến lược</th><th>Loại</th>
                  <th className="!text-right">Final</th><th className="!text-right">Ret/năm</th>
                  <th className="!text-right">Sharpe</th><th className="!text-right">MaxDD</th>
                  <th className="!text-right">TE</th><th className="!text-right">IR</th>
                  <th className="!text-right">Max w</th><th className="!text-right">Số mã</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => {
                  const m = r.metrics
                  const nHeld = Object.values(r.weights ?? {}).filter(w => w > 0).length
                  return (
                    <tr key={r.id} className={r.error ? 'bg-vps-red/40' : ''}>
                      <td className="font-medium max-w-[240px] truncate" title={r.error ?? r.name}>
                        {r.name}{r.error && <span className="ml-1 text-[10px] text-vps-deep">⚠ lỗi</span>}
                      </td>
                      <td><span className={`vps-chip ${r.kind === 'preset' ? 'bg-vps-lavender text-vps-deep' : 'bg-vps-blue text-vps-black'}`}>{r.kind}</span></td>
                      <Num v={m.final} /><Num v={m.ann_ret_pct} suffix="%" />
                      <Num v={m.sharpe} /><Num v={m.maxdd_pct} suffix="%" />
                      <Num v={m.te_vs_bench_pct} suffix="%" /><Num v={m.information_ratio} />
                      <Num v={m.max_weight_pct} suffix="%" />
                      <td className="text-right tabular-nums">{r.error ? '—' : nHeld}</td>
                    </tr>
                  )
                })}
                {rows.length === 0 && <tr><td colSpan={10} className="text-vps-gray">Chưa có kết quả.</td></tr>}
              </tbody>
            </table>
          </div>
          <p className="text-[10px] text-vps-gray mt-1">Preset chạy toàn bộ rổ cổ phiếu / cap 25% / từ 2020-01-02. Saved chạy đúng config lúc lưu, end_date = phiên cuối có data. Metrics GROSS.</p>
        </div>
      </div>
    </div>
  )
}

/** Schedule card: view and edit run time, weekday-only and the T / T-1 cut-off. */
function ScheduleCard({ st, onSaved }: { st: JobsStatus | null; onSaved: () => void }) {
  const [edit, setEdit] = useState(false)
  const [time, setTime] = useState('16:00')
  const [dataDay, setDataDay] = useState('T')
  const [weekdays, setWeekdays] = useState(true)
  const [enabled, setEnabled] = useState(true)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const open = async () => {
    setErr('')
    try {
      const { settings } = await getSchedule()
      setTime(settings.scheduler_time); setDataDay(settings.job_data_day)
      setWeekdays(settings.scheduler_weekdays_only === '1')
      setEnabled(settings.scheduler_enabled === '1')
      setEdit(true)
    } catch (e: any) { setErr(e?.response?.data?.detail ?? String(e)) }
  }
  const save = async () => {
    setBusy(true); setErr('')
    try {
      await saveSchedule({ scheduler_enabled: enabled, scheduler_time: time,
                           scheduler_weekdays_only: weekdays, job_data_day: dataDay })
      setEdit(false); onSaved()
    } catch (e: any) { setErr(e?.response?.data?.detail ?? String(e)) }
    finally { setBusy(false) }
  }

  const s = st?.scheduler
  return (
    <div className="vps-card p-3">
      <div className="flex items-center justify-between mb-1.5">
        <span className="vps-label">Lịch chạy tự động</span>
        {!edit && <button onClick={open} className="text-[11px] text-vps-violet hover:underline">Sửa</button>}
      </div>

      {!edit ? (
        <>
          <div className="flex items-center gap-2"><StatusDot ok={!!s?.enabled} />
            <span className="text-sm font-medium">
              {s?.enabled ? `${s.time} ${s.weekdays_only ? '· T2–T6' : '· mỗi ngày'}` : 'Đang tắt'}
            </span></div>
          <div className="text-xs text-vps-gray mt-1">
            Lấy dữ liệu tới <b className="text-vps-deep">{dayLabel(s?.data_day)}</b>
          </div>
          <div className="text-[11px] text-vps-gray">Kế tiếp: {fmtTs(s?.next_run)}</div>
          <div className="text-[11px] text-vps-gray">
            Lần cuối: {fmtTs(s?.last_run)} {s?.last_status ? `(${s.last_status})` : ''}
          </div>
        </>
      ) : (
        <div className="space-y-1.5">
          <label className="flex items-center gap-1.5 text-xs">
            <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />
            Bật chạy tự động
          </label>
          <label className="flex items-center gap-2 text-xs">
            Giờ chạy
            <input type="time" value={time} onChange={e => setTime(e.target.value)}
              className="vps-input text-xs py-0.5" />
          </label>
          <label className="flex items-center gap-2 text-xs" title="Chạy cuối phiên thì chọn T; chạy sáng sớm hôm sau thì chọn T-1.">
            Dữ liệu tới
            <select value={dataDay} onChange={e => setDataDay(e.target.value)} className="vps-input text-xs py-0.5">
              <option value="T">phiên hôm nay (T)</option>
              <option value="T-1">phiên hôm trước (T-1)</option>
            </select>
          </label>
          <label className="flex items-center gap-1.5 text-xs">
            <input type="checkbox" checked={weekdays} onChange={e => setWeekdays(e.target.checked)} />
            Chỉ chạy T2–T6
          </label>
          <div className="flex gap-1 pt-0.5">
            <button onClick={save} disabled={busy} className="vps-btn-primary text-[11px] py-0.5 px-2">
              {busy ? '…' : 'Lưu'}
            </button>
            <button onClick={() => setEdit(false)} className="vps-btn-ghost text-[11px] py-0.5 px-2">Hủy</button>
          </div>
        </div>
      )}
      {err && <div className="text-[11px] text-vps-deep mt-1">{err}</div>}
    </div>
  )
}

function Num({ v, suffix = '' }: { v: number | string | undefined; suffix?: string }) {
  return <td className="text-right tabular-nums">{v === undefined || v === null ? '—' : `${v}${suffix}`}</td>
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="vps-card p-3">
      <div className="vps-label mb-1.5">{title}</div>
      {children}
    </div>
  )
}

function RunSummary({ run }: { run: DailyRun }) {
  const s = run.summary?.steps ?? {}
  const line = (k: string, v: any) => {
    if (!v) return null
    if (v.error) return <div key={k}><b>{k}</b>: <span className="text-vps-deep">lỗi — {String(v.error).slice(0, 120)}</span></div>
    if (k === 'sync') return (
      <div key={k}>
        <b>sync{v.full ? ' (toàn bộ)' : ''}</b>: {v.ok} mã OK, +{v.rows_new} dòng,{' '}
        {v.errors?.length ?? 0} lỗi, data tới {v.data_end}
        {v.stale && <div className="text-vps-deep">⚠ {v.stale}</div>}
      </div>
    )
    if (k === 'backtest') return <div key={k}><b>backtest</b>: {v.ok} OK / {v.errors} lỗi</div>
    return <div key={k}><b>{k}</b>: {v.rows} ngày → {v.end}</div>
  }
  return (
    <div className="mt-3 pt-2 border-t border-vps-lavender text-[11px] text-vps-black space-y-0.5">
      <div className="vps-label mb-1">Run #{run.id} · {run.status}</div>
      {['sync', 'build_ftse', 'build_vnindex', 'backtest'].map(k => line(k, s[k]))}
      {run.summary?.error && <div className="text-vps-deep">{run.summary.error}</div>}
    </div>
  )
}
