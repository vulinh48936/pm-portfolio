import axios from 'axios'
import type {
  Defaults, LabConfig, BacktestResult, CompareResult, WeightGridResult,
  LiquidityResult, StrategySpec, AttributionResult, SavedStrategy, StrategyExplanation,
  JobsStatus, JobsResults, ScheduleSettings, SchedulerState,
  WeightList, WeightPeriod, WeightSaveResult, Constituent,
} from './types'

const api = axios.create({ baseURL: '/api' })

export const getDefaults = (): Promise<Defaults> =>
  api.get('/lab/config/defaults').then(r => r.data)

export const generateStrategy = (nl_request: string, config: LabConfig): Promise<{ code: string }> =>
  api.post('/lab/strategy/generate', { nl_request, config }).then(r => r.data)

export const runBacktest = (spec: StrategySpec, config: LabConfig): Promise<BacktestResult> =>
  api.post('/lab/strategy/backtest', { spec, config }).then(r => r.data)

export const runCompare = (
  strategies: { name: string; spec: StrategySpec }[], config: LabConfig,
): Promise<CompareResult> =>
  api.post('/lab/strategy/compare', { strategies, config }).then(r => r.data)

export const runWeightGrid = (
  strategies: { name: string; spec: StrategySpec }[], config: LabConfig, date?: string,
  forceRebalance = false,
): Promise<WeightGridResult> =>
  api.post('/lab/strategy/weight-grid',
    { strategies, config, date, force_rebalance: forceRebalance }).then(r => r.data)

export const runAttribution = (
  spec: StrategySpec, config: LabConfig, window_start?: string,
): Promise<AttributionResult> =>
  api.post('/lab/strategy/attribution', { spec, config, window_start }).then(r => r.data)

export const explainStrategy = (
  spec: StrategySpec, config: LabConfig,
): Promise<StrategyExplanation> =>
  api.post('/lab/strategy/explain', { spec, config }).then(r => r.data)

export const runLiquidity = (
  spec: StrategySpec, config: LabConfig,
  params: { target_aum?: number; redeem_pct?: number; participation?: number },
): Promise<LiquidityResult> =>
  api.post('/lab/strategy/liquidity', { spec, config, ...params }).then(r => r.data)

export const saveStrategy = (body: {
  name: string; nl_prompt: string; code: string
  config: Record<string, unknown>; metrics: Record<string, unknown>
  rebalance_schedule?: string; move_policy?: string
}): Promise<{ id: number }> =>
  api.post('/lab/strategies', body).then(r => r.data)

export const listStrategies = (): Promise<SavedStrategy[]> =>
  api.get('/lab/strategies').then(r => r.data)

export const deleteStrategy = (id: number): Promise<void> =>
  api.delete(`/lab/strategies/${id}`).then(() => undefined)

// Daily job
export const getJobsStatus = (): Promise<JobsStatus> =>
  api.get('/lab/jobs/status').then(r => r.data)

export const runJob = (body: { sync?: boolean; end?: string | null; include_presets?: boolean
                               include_saved?: boolean; full_sync?: boolean }) =>
  api.post('/lab/jobs/run', body).then(r => r.data)

export const getJobsResults = (run_id?: number): Promise<JobsResults> =>
  api.get('/lab/jobs/results', { params: run_id ? { run_id } : {} }).then(r => r.data)

export const getSchedule = (): Promise<{ settings: ScheduleSettings; scheduler: SchedulerState }> =>
  api.get('/lab/jobs/schedule').then(r => r.data)

export const saveSchedule = (
  body: Partial<{ scheduler_enabled: boolean; scheduler_time: string; scheduler_tz: string
                  scheduler_weekdays_only: boolean; job_data_day: string }>,
): Promise<{ settings: ScheduleSettings; scheduler: SchedulerState }> =>
  api.put('/lab/jobs/schedule', body).then(r => r.data)

export const pingMarketApi = (): Promise<{ ok: boolean; url: string | null; detail: string | null }> =>
  api.get('/lab/jobs/market-ping').then(r => r.data)


// Benchmark basket
export const listWeightPeriods = (): Promise<WeightList> =>
  api.get('/lab/weights').then(r => r.data)

export const getWeightPeriod = (effectiveDate: string): Promise<WeightPeriod> =>
  api.get(`/lab/weights/${effectiveDate}`).then(r => r.data)

export const saveWeightPeriod = (
  effectiveDate: string, constituents: Constituent[], period?: string,
): Promise<WeightSaveResult> =>
  api.put(`/lab/weights/${effectiveDate}`, { constituents, period }).then(r => r.data)

export const deleteWeightPeriod = (effectiveDate: string) =>
  api.delete(`/lab/weights/${effectiveDate}`).then(r => r.data)

export const parseWeightPaste = (
  text: string,
): Promise<{ constituents: Constituent[]; num_stocks: number; total_weight_pct: number }> =>
  api.post('/lab/weights/parse', { text }).then(r => r.data)
