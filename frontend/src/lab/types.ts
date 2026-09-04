export interface UniverseStock { ticker: string; name: string; sector: string }

export interface Defaults {
  /** false = the snapshot is empty (fresh install, job never ran); every date bound is null */
  data_ready: boolean
  universe: UniverseStock[]
  default_cap: number
  start_date: string | null
  end_date: string | null       // defaults to the last session with data
  min_date: string | null       // date bounds: prices intersected with index_ftse
  max_date: string | null
  presets: string[]
  preset_code: Record<string, string>
  features: string[]
}

export type Metrics = Record<string, number>

export interface LabConfig {
  universe?: string[]
  start_date: string
  end_date?: string | null
  cap: number | null
  aum_bn?: number
  adtv_floor_bn?: number | null
  max_names?: number | null
  min_names?: number | null
}

export interface Feasibility {
  min_aum_bn: number
  recommended_aum_bn: number
  bottleneck_ticker: string | null
  bottleneck_weight_pct: number
  te_curve: { aum_bn: number; te_pct: number; is_current?: boolean }[]
}

export interface AttributionRow {
  ticker: string
  sector: string
  w_strat_pct: number
  w_ftse_pct: number
  wdiff_pct: number
  stock_ret_pct: number
  contrib_pp: number
}

export interface AttributionResult {
  window_start: string
  window_end: string
  total_contrib_pp: number
  rows: AttributionRow[]
}

export interface BacktestResult {
  metrics: Metrics
  dates: string[]
  port_cum: number[]
  bench_cum: number[]
  vnindex_cum: number[]
  max_weight_series: number[]
  // invested share; 100 = fully invested, below that the overlay holds cash; null without an overlay
  exposure_series: number[] | null
  weights_latest: Record<string, number>
  feasibility: Feasibility
  warnings: string[]
  rebalance_schedule: string
  move_policy: string
}

export type IndexMetrics = Record<string, number | string>

export interface CompareResult {
  dates: string[]
  bench_cum: number[]
  vnindex_cum: number[]
  bench_metrics?: IndexMetrics
  vnindex_metrics?: IndexMetrics
  strategies: { name: string; metrics: Metrics; port_cum: number[]; max_weight_series: number[]; exposure_series?: number[] | null; capacity?: Capacity }[]
}

export interface WeightGridResult {
  date: string                      // session the weights are taken from
  columns: string[]
  rows: Record<string, string | number>[]
  forced: boolean                   // true = weights AFTER a forced rebalance
  rebalance_date: string | null     // order date; null unless forced
}

// Liquidity and capacity (flow stress)
export interface LiqEventRow {
  ticker: string
  weight_pct: number
  position_bn: number
  required_bn: number
  available_bn: number
  shortfall_pct: number
  spill_days: number
  slippage_pct: number
  slippage_crash_pct: number
  // rebalance tab only: weights before and after the last rebalance, plus the signed delta
  weight_prev_pct?: number
  weight_new_pct?: number
  delta_pct?: number
}

export interface Capacity {
  bottleneck_L: number
  binding_ticker: string | null
  max_redeem_pct: number
}

export interface LiquidityResult {
  target_aum: number
  participation_pct: number
  window: number
  bottleneck_L: number
  binding_ticker: string | null
  max_redeem_pct: number
  capacity_curve: { aum_bn: number; max_redeem_pct: number }[]
  rebalance_date?: string | null
  per_event: { redeem: LiqEventRow[]; rebalance: LiqEventRow[] }
  lock_flags: { ticker: string; liq_bn: number; reason: string }[]
  adtv_inflation: number
  short_history: string[]
  error?: string
}

export type StrategySpec = { code?: string | null; preset?: string | null }

export interface ExplanationComponent {
  label: string
  formula: string | null
  meaning: string
  role: 'risk' | 'return' | 'rebalance' | 'other'
}
export interface StrategyExplanation {
  title: string
  summary: string
  components: ExplanationComponent[]
  rebalance: string
  recommendations: string[]
}

export interface SavedStrategy {
  /** metrics from the latest daily run; never overwrites `metrics` captured at save time */
  latest?: { metrics: Metrics; data_end: string; error: string | null } | null
  id: number
  name: string
  nl_prompt: string
  code: string
  config: Record<string, unknown>
  metrics: Metrics
  rebalance_schedule: string
  move_policy: string
  status: string
  created_at: string
  updated_at: string
}

// Daily job
export interface DailyRun {
  id: number
  status: 'running' | 'ok' | 'partial' | 'failed' | string
  trigger: string
  data_end: string
  started_at: string | null
  finished_at: string | null
  summary: Record<string, any>
}

export interface ScheduleSettings {
  scheduler_enabled: string          // "1" | "0"
  scheduler_time: string             // "HH:MM"
  scheduler_tz: string
  scheduler_weekdays_only: string    // "1" | "0"
  job_data_day: string               // "T" | "T-1"
}

export interface SchedulerState {
  enabled: boolean; alive: boolean; time: string; tz: string
  weekdays_only: boolean; data_day: string
  next_run: string | null; last_run: string | null; last_status: string | null
}

export interface JobsStatus {
  scheduler: SchedulerState
  running: boolean
  market_api: { url: string | null; ccp_url: string | null; configured: boolean }
  llm: { ok: boolean; base_url: string; model: string; detail: string | null }
  data: { price_start: string; price_end: string; index_start: string; index_end: string }
  runs: DailyRun[]
}

export interface DailyResultRow {
  id: number
  kind: 'preset' | 'saved' | string
  ref: string
  name: string
  data_end: string
  metrics: Metrics
  weights: Record<string, number>
  error: string | null
}

export interface JobsResults { run: DailyRun | null; results: DailyResultRow[] }


// Benchmark basket (weight.json)
export interface Constituent { ticker: string; weight_pct: number }

export interface WeightPeriodSummary {
  effective_date: string
  period: string
  num_stocks: number
  total_weight_pct: number
  sum_ok: boolean
}

export interface WeightPeriod extends WeightPeriodSummary {
  constituents: Constituent[]
}

export interface WeightList {
  source: string
  note: string
  periods: WeightPeriodSummary[]
}

export interface WeightSaveResult extends WeightPeriodSummary {
  created: boolean
  warnings: string[]
  benchmark?: { rows: number; start: string; end: string }
  benchmark_error?: string
}
