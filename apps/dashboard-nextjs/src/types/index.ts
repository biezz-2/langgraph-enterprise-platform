export interface Subagent {
  id: string
  name: string
  pod: string
  role: string
  version: string
  trust_level: string
  budget_config: {
    max_usd: number
    max_tokens: number
    max_wall_clock_s?: number
    max_steps?: number
    parallel_max?: number
  }
  capabilities: string[]
  is_active: boolean
  model_policy?: string
  tool_grants?: string[]
  memory_scope?: string
  circuit_breaker?: "closed" | "open" | "half-open"
  consecutive_failures?: number
}

export type KanbanPhaseStatus =
  | "BACKLOG"
  | "IN PROGRESS"
  | "IMPLEMENTED"
  | "IN VALIDATION"
  | "VALIDATED"
  | "REWORK"

export interface KanbanBoard {
  id: string
  name: string
  columns: KanbanColumn[]
  created_at?: number | string
  updated_at?: number | string
}

export interface KanbanColumn {
  id: string
  board_id?: string
  name: string
  order?: number
  order_idx?: number
  cards: KanbanCard[]
}

export interface KanbanCard {
  id: string
  column_id?: string
  title: string
  description: string
  status?: string
  phase_ref?: string
  severity?: "BLOCKER" | "MAJOR" | "MINOR" | null
  priority: "low" | "medium" | "high" | "critical"
  assigned_to?: string | null
  created_at?: number | string
  updated_at?: number | string
  metadata?: Record<string, unknown>
  metadata_json?: string
}

export interface MatrixConfiguration {
  id: string
  name: string
  description: string
  alpha: number
  beta: number
  gamma: number
  n_min: number
  enabled: boolean
  created_at?: number | string
}

export interface DAGStep {
  id: string
  node_name: string
  subagent: string
  status: "completed" | "running" | "failed" | "pending" | "interrupted"
  latency_ms: number
  token_usage: {
    input_tokens: number
    output_tokens: number
    total_tokens: number
    cost_usd: number
  }
  input_preview?: Record<string, unknown> | string
  output_preview?: Record<string, unknown> | string
  started_at: string
  completed_at?: string
}

export interface RunCheckpoint {
  checkpoint_id: string
  step_index: number
  node: string
  timestamp: string
  state_snapshot: Record<string, unknown>
}

export interface Run {
  run_id: string
  thread_id: string
  objective: string
  status: "completed" | "running" | "failed" | "interrupted"
  created_at: number | string
  updated_at?: number | string
  final_answer?: string
  budget_used?: number
  current_subagent?: string | null
  total_latency_s?: number
  total_tokens?: number
  steps?: DAGStep[]
  checkpoints?: RunCheckpoint[]
}

export interface HITLItem {
  id: string
  interrupt_id: string
  thread_id: string
  run_id: string
  subagent: string
  action_type: string
  description: string
  risk_level: "low" | "medium" | "high" | "critical"
  proposed_payload: Record<string, unknown> | string
  created_at: string | number
  status: "pending" | "approved" | "rejected" | "modified"
  resolved_by?: string
  resolved_at?: string | number
  notes?: string
}

export interface MemoryFact {
  fact_id: string
  subject: string
  predicate: string
  object: string
  valid_at: number | string
  invalid_at: number | string | null
  created_at: number | string
  expired_at?: number | string | null
  episode_run_id?: string | null
  pii_redacted: boolean | number
  similarity?: number
}

export interface AuditLogEntry {
  log_id: string
  actor: string
  action: string
  scope: string
  args_hash: string
  prev_hash: string
  curr_hash: string
  result_status: string
  created_at: string | number
  details?: Record<string, unknown> | string
}

export interface OWASPGuardrailLog {
  id: string
  rule_id: "LLM01" | "LLM02" | "LLM03" | "LLM04" | "LLM05" | "LLM06" | "LLM07" | "LLM08" | "LLM09" | "LLM10"
  rule_name: string
  subagent: string
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
  mitigation: string
  detected_payload: string
  action_taken: "BLOCKED" | "SANITIZED" | "INTERRUPTED" | "MONITORED"
  timestamp: string | number
}

export interface CircuitBreakerEvent {
  id: string
  subagent: string
  state: "CLOSED" | "OPEN" | "HALF-OPEN"
  consecutive_failures: number
  trigger_reason: string
  timestamp: string | number
  recovery_action?: string
}

export interface CorrelationEdge {
  source_subagent: string
  target_subagent: string
  handoff_rate: number
  npmi_coactivation: number
  success_lift: number
  latency_coupling: number
  composite_weight: number
  polarity: string
  sample_count: number
  updated_at?: string | number
}

export interface SystemHealth {
  status: string
  version: string
  platform: string
  subagents_active: number
  supervisor: string
  storage: string
  mcp_admin: string
  uptime_s?: number
  avg_latency_ms?: number
  active_circuits_open?: number
}

export interface FastMCPTool {
  name: string
  description: string
  annotations?: {
    readOnlyHint?: boolean
    destructiveHint?: boolean
    idempotentHint?: boolean
    openWorldHint?: boolean
  }
  parameters?: {
    type: string
    properties?: Record<string, { type: string; description?: string; enum?: string[] }>
    required?: string[]
  }
}
