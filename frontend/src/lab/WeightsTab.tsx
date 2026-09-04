import { useEffect, useState } from 'react'
import {
  listWeightPeriods, getWeightPeriod, saveWeightPeriod, deleteWeightPeriod, parseWeightPaste,
} from './api'
import type { WeightList, WeightPeriod, Constituent } from './types'

const sumOf = (rows: Constituent[]) =>
  Math.round(rows.reduce((a, r) => a + (Number(r.weight_pct) || 0), 0) * 1e4) / 1e4

/** Benchmark tab: view, add, edit and delete review periods of the FTSE basket.
 *  Each save rebuilds the benchmark on the backend, so comparisons update at once. */
export function WeightsTab() {
  const [list, setList] = useState<WeightList | null>(null)
  const [sel, setSel] = useState<string | null>(null)
  const [detail, setDetail] = useState<WeightPeriod | null>(null)
  const [draft, setDraft] = useState<Constituent[] | null>(null)   // non-null while editing
  const [draftDate, setDraftDate] = useState('')
  const [msg, setMsg] = useState('')
  const [warns, setWarns] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [paste, setPaste] = useState('')
  const [showPaste, setShowPaste] = useState(false)

  const refresh = async (keep?: string) => {
    const l = await listWeightPeriods()
    setList(l)
    const pick = keep ?? sel ?? l.periods[l.periods.length - 1]?.effective_date ?? null
    if (pick) { setSel(pick); setDetail(await getWeightPeriod(pick).catch(() => null)) }
  }
  useEffect(() => { refresh().catch(e => setMsg(String(e))) }, [])

  const open = async (d: string) => {
    setSel(d); setDraft(null); setWarns([]); setMsg('')
    setDetail(await getWeightPeriod(d))
  }

  const startEdit = () => {
    if (!detail) return
    setDraftDate(detail.effective_date)
    setDraft(detail.constituents.map(c => ({ ...c })))
    setWarns([]); setMsg('')
  }
  const startNew = () => {
    // A new period usually differs by a few tickers, so start from the one on screen.
    setDraftDate('')
    setDraft(detail ? detail.constituents.map(c => ({ ...c })) : [{ ticker: '', weight_pct: 0 }])
    setWarns([]); setMsg('')
  }

  const save = async () => {
    if (!draft) return
    if (!/^\d{4}-\d{2}-\d{2}$/.test(draftDate)) { setMsg('Chọn ngày hiệu lực trước khi lưu.'); return }
    setBusy(true); setMsg(''); setWarns([])
    try {
      const rows = draft.filter(r => r.ticker.trim() && Number(r.weight_pct) > 0)
      const res = await saveWeightPeriod(draftDate, rows)
      setWarns(res.warnings ?? [])
      setMsg(res.benchmark_error
        ? `Đã lưu nhưng dựng benchmark lỗi: ${res.benchmark_error}`
        : `✓ Đã ${res.created ? 'thêm' : 'cập nhật'} kỳ ${res.effective_date} và dựng lại benchmark`)
      setDraft(null)
      await refresh(draftDate)
    } catch (e: any) { setMsg(e?.response?.data?.detail ?? String(e)) }
    finally { setBusy(false) }
  }

  const del = async (d: string) => {
    if (!confirm(`Xóa kỳ ${d}? Benchmark sẽ được dựng lại theo các kỳ còn lại.`)) return
    setBusy(true); setMsg('')
    try {
      const res: any = await deleteWeightPeriod(d)
      // Do not call refresh() here: `sel` still points at the period just deleted
      // (setState is async), so it would reload it and get a 404. Pick the latest instead.
      const l = await listWeightPeriods()
      setList(l)
      const last = l.periods[l.periods.length - 1]?.effective_date ?? null
      setSel(last)
      setDetail(last ? await getWeightPeriod(last) : null)
      setDraft(null)
      setMsg(res?.benchmark_error
        ? `Đã xóa kỳ ${d} nhưng dựng benchmark lỗi: ${res.benchmark_error}`
        : `✓ Đã xóa kỳ ${d} và dựng lại benchmark`)
    } catch (e: any) { setMsg(e?.response?.data?.detail ?? String(e)) }
    finally { setBusy(false) }
  }

  const applyPaste = async () => {
    setBusy(true); setMsg('')
    try {
      const r = await parseWeightPaste(paste)
      setDraft(r.constituents)
      setShowPaste(false); setPaste('')
      setMsg(`✓ Đã đọc ${r.num_stocks} mã, tổng ${r.total_weight_pct}%`)
    } catch (e: any) { setMsg(e?.response?.data?.detail ?? String(e)) }
    finally { setBusy(false) }
  }

  const rows = draft ?? detail?.constituents ?? []
  const total = sumOf(rows)
  const editing = draft !== null

  return (
    <div className="space-y-4">
      <div className="vps-card p-4 border-l-4 !border-l-vps-violet">
        <div className="flex flex-wrap items-center gap-3">
          <div>
            <div className="vps-label">Rổ chuẩn theo kỳ review</div>
            <div className="text-xs text-vps-gray mt-0.5">
              Trọng số mục tiêu FTSE dùng làm benchmark và làm neo cho universe động.
              Lưu xong benchmark được dựng lại ngay.
            </div>
          </div>
          <div className="ml-auto flex gap-2">
            <button onClick={startNew} disabled={busy} className="vps-btn-primary text-xs">+ Thêm kỳ</button>
            {detail && !editing && (
              <>
                <button onClick={startEdit} disabled={busy} className="vps-btn-outline text-xs">Sửa kỳ này</button>
                <button onClick={() => del(detail.effective_date)} disabled={busy}
                  className="vps-btn text-xs border border-vps-gray text-vps-deep hover:bg-vps-red">Xóa kỳ</button>
              </>
            )}
          </div>
        </div>
        {msg && (
          <p className={`text-xs mt-2 rounded px-2 py-1 ${msg.startsWith('✓') ? 'bg-vps-green text-vps-black' : 'bg-vps-red text-vps-deep'}`}>{msg}</p>
        )}
        {warns.map((w, i) => (
          <p key={i} className="text-xs mt-1 bg-vps-yellow text-vps-black rounded px-2 py-1">⚠ {w}</p>
        ))}
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        {/* Period list */}
        <div className="vps-card p-4">
          <div className="vps-label mb-2">Các kỳ ({list?.periods.length ?? 0})</div>
          <div className="max-h-[560px] overflow-y-auto">
            <table className="vps-table text-xs w-full">
              <thead className="sticky top-0 bg-white">
                <tr><th>Hiệu lực</th><th className="!text-right">Số mã</th><th className="!text-right">Tổng %</th></tr>
              </thead>
              <tbody>
                {[...(list?.periods ?? [])].reverse().map(p => (
                  <tr key={p.effective_date} onClick={() => open(p.effective_date)}
                    className={`cursor-pointer hover:bg-vps-offwhite ${sel === p.effective_date ? 'bg-vps-lavender/50' : ''}`}>
                    <td className="font-medium tabular-nums">{p.effective_date}</td>
                    <td className="text-right tabular-nums">{p.num_stocks}</td>
                    <td className={`text-right tabular-nums ${p.sum_ok ? '' : 'text-vps-deep font-semibold'}`}
                      title={p.sum_ok ? '' : 'Tổng lệch quá 0.5đ% so với 100%'}>
                      {p.total_weight_pct}{p.sum_ok ? '' : ' ⚠'}
                    </td>
                  </tr>
                ))}
                {!list?.periods.length && <tr><td colSpan={3} className="text-vps-gray">Chưa có kỳ nào.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        {/* Detail and editor */}
        <div className="vps-card p-4 lg:col-span-2">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="vps-label">
              {editing ? (draftDate && draftDate === detail?.effective_date ? 'Sửa kỳ' : 'Kỳ mới') : 'Chi tiết kỳ'}
            </span>
            {editing ? (
              <>
                <input type="date" value={draftDate} onChange={e => setDraftDate(e.target.value)}
                  className="vps-input text-xs" title="Ngày rổ mới bắt đầu có hiệu lực" />
                <button onClick={() => setShowPaste(v => !v)} className="vps-btn-ghost text-[11px] py-0.5 px-2">
                  Dán từ bảng FTSE
                </button>
                <button onClick={() => setDraft([...(draft ?? []), { ticker: '', weight_pct: 0 }])}
                  className="vps-btn-ghost text-[11px] py-0.5 px-2">+ Dòng</button>
                <div className="ml-auto flex gap-1">
                  <button onClick={save} disabled={busy} className="vps-btn-primary text-xs">
                    {busy ? '…' : 'Lưu & dựng lại benchmark'}
                  </button>
                  <button onClick={() => { setDraft(null); setWarns([]) }} className="vps-btn-ghost text-xs">Hủy</button>
                </div>
              </>
            ) : (
              <span className="text-xs text-vps-gray">
                {detail ? `${detail.effective_date} · ${detail.num_stocks} mã` : 'Chọn một kỳ bên trái'}
              </span>
            )}
            <span className={`ml-auto vps-chip ${Math.abs(total - 100) <= 0.5 ? 'bg-vps-green text-vps-black' : 'bg-vps-yellow text-vps-black'}`}>
              Tổng {total}%
            </span>
          </div>

          {showPaste && editing && (
            <div className="mb-2">
              <textarea value={paste} onChange={e => setPaste(e.target.value)} rows={5}
                placeholder={'Dán mỗi dòng một mã, ví dụ:\nVIC\t28,32\nVHM\t8,54\nHPG 5.1'}
                className="vps-input w-full text-xs font-mono" />
              <div className="flex gap-2 mt-1">
                <button onClick={applyPaste} disabled={busy || !paste.trim()} className="vps-btn-primary text-xs">Đọc vào bảng</button>
                <button onClick={() => { setShowPaste(false); setPaste('') }} className="vps-btn-ghost text-xs">Đóng</button>
              </div>
            </div>
          )}

          <div className="max-h-[480px] overflow-y-auto">
            <table className="vps-table text-xs w-full">
              <thead className="sticky top-0 bg-white">
                <tr><th>#</th><th>Mã</th><th className="!text-right">Weight %</th>{editing && <th></th>}</tr>
              </thead>
              <tbody>
                {rows.map((c, i) => (
                  <tr key={i}>
                    <td className="text-vps-gray tabular-nums">{i + 1}</td>
                    <td className="font-medium">
                      {editing ? (
                        <input value={c.ticker} onChange={e => {
                          const next = [...(draft ?? [])]; next[i] = { ...c, ticker: e.target.value.toUpperCase() }; setDraft(next)
                        }} className="vps-input text-xs w-24 py-0.5" placeholder="VIC" />
                      ) : c.ticker}
                    </td>
                    <td className="text-right tabular-nums">
                      {editing ? (
                        <input type="number" step="0.0001" value={c.weight_pct} onChange={e => {
                          const next = [...(draft ?? [])]; next[i] = { ...c, weight_pct: Number(e.target.value) }; setDraft(next)
                        }} className="vps-input text-xs w-28 py-0.5 text-right" />
                      ) : c.weight_pct}
                    </td>
                    {editing && (
                      <td className="text-right">
                        <button onClick={() => setDraft((draft ?? []).filter((_, j) => j !== i))}
                          title="Xóa mã khỏi kỳ" className="text-vps-deep px-1">✕</button>
                      </td>
                    )}
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={editing ? 4 : 3} className="text-vps-gray">Chưa có mã nào.</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <p className="text-[10px] text-vps-gray mt-1">
            Mã không nằm trong rổ dữ liệu sẽ bị bỏ qua khi dựng benchmark — cảnh báo sẽ hiện khi lưu.
            Sau khi sửa, chạy lại backtest ở tab Operations để cập nhật số liệu các chiến lược.
          </p>
        </div>
      </div>
    </div>
  )
}
