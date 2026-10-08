-- =============================================================================
-- LGP v2.0 Enterprise Persistence Schema
-- Kompatibel: SQLite (WAL mode) & PostgreSQL 16+
-- =============================================================================

-- PRAGMA untuk SQLite (Dev Standalone):
-- PRAGMA journal_mode = WAL;
-- PRAGMA synchronous = NORMAL;
-- PRAGMA foreign_keys = ON;
-- PRAGMA busy_timeout = 5000;

-- 1. SUBAGENT REGISTRY
CREATE TABLE IF NOT EXISTS subagent_registry (
    id VARCHAR(64) PRIMARY KEY,
    role VARCHAR(64) NOT NULL,
    name VARCHAR(128) NOT NULL,
    capabilities JSON NOT NULL DEFAULT '[]',
    input_schema JSON NOT NULL DEFAULT '{}',
    output_schema JSON NOT NULL DEFAULT '{}',
    tool_grants JSON NOT NULL DEFAULT '[]',
    model_policy JSON NOT NULL DEFAULT '{}',
    budget_config JSON NOT NULL DEFAULT '{}',
    memory_scope VARCHAR(128) NOT NULL,
    trust_level VARCHAR(16) NOT NULL DEFAULT 'medium',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_subagent_trust_level CHECK (trust_level IN ('low', 'medium', 'high'))
);

CREATE INDEX IF NOT EXISTS idx_subagent_role ON subagent_registry(role);
CREATE INDEX IF NOT EXISTS idx_subagent_active ON subagent_registry(is_active);

-- 2. THREADS
CREATE TABLE IF NOT EXISTS threads (
    thread_id VARCHAR(64) PRIMARY KEY,
    metadata JSON NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. RUNS
CREATE TABLE IF NOT EXISTS runs (
    run_id VARCHAR(64) PRIMARY KEY,
    thread_id VARCHAR(64) NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    current_subagent VARCHAR(64) REFERENCES subagent_registry(id) ON DELETE SET NULL,
    context_packet JSON NOT NULL DEFAULT '{}',
    budget_allocated JSON NOT NULL DEFAULT '{}',
    budget_spent JSON NOT NULL DEFAULT '{}',
    checkpoints_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_run_status CHECK (status IN ('pending', 'running', 'interrupted', 'completed', 'failed', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_runs_thread_id ON runs(thread_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_current_subagent ON runs(current_subagent);
CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at DESC);

-- 4. CHECKPOINTS & STATE DIFFS
CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id VARCHAR(64) PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    thread_id VARCHAR(64) NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    parent_checkpoint_id VARCHAR(64) REFERENCES checkpoints(checkpoint_id) ON DELETE SET NULL,
    state_hash VARCHAR(64) NOT NULL,
    state_data JSON NOT NULL,
    step INTEGER NOT NULL DEFAULT 0,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_run_step ON checkpoints(run_id, step);
CREATE INDEX IF NOT EXISTS idx_checkpoints_run_state_hash ON checkpoints(run_id, state_hash);
CREATE INDEX IF NOT EXISTS idx_checkpoints_timestamp ON checkpoints(timestamp DESC);

CREATE TABLE IF NOT EXISTS state_diffs (
    diff_id VARCHAR(64) PRIMARY KEY,
    checkpoint_id VARCHAR(64) NOT NULL REFERENCES checkpoints(checkpoint_id) ON DELETE CASCADE,
    run_id VARCHAR(64) NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    from_checkpoint_id VARCHAR(64) REFERENCES checkpoints(checkpoint_id) ON DELETE SET NULL,
    to_checkpoint_id VARCHAR(64) NOT NULL REFERENCES checkpoints(checkpoint_id) ON DELETE CASCADE,
    node_name VARCHAR(64),
    diff_data JSON NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_state_diffs_run_ckpt ON state_diffs(run_id, checkpoint_id);
CREATE INDEX IF NOT EXISTS idx_state_diffs_timestamp ON state_diffs(timestamp DESC);

-- 5. TELEMETRY EVENTS
CREATE TABLE IF NOT EXISTS telemetry_events (
    event_id VARCHAR(64) PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    subagent_id VARCHAR(64) NOT NULL REFERENCES subagent_registry(id) ON DELETE CASCADE,
    event_type VARCHAR(32) NOT NULL,
    payload JSON NOT NULL DEFAULT '{}',
    tokens INTEGER NOT NULL DEFAULT 0,
    cost NUMERIC(10, 6) NOT NULL DEFAULT 0.0,
    latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_telemetry_event_type CHECK (
        event_type IN ('node.start', 'node.end', 'tool.call', 'delegate', 'state.read', 'state.write', 'interrupt', 'error')
    )
);

CREATE INDEX IF NOT EXISTS idx_telemetry_run_id ON telemetry_events(run_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_subagent_event ON telemetry_events(subagent_id, event_type);
CREATE INDEX IF NOT EXISTS idx_telemetry_run_created ON telemetry_events(run_id, created_at);

-- 6. CORRELATION EDGES
CREATE TABLE IF NOT EXISTS correlation_edges (
    source_subagent VARCHAR(64) NOT NULL REFERENCES subagent_registry(id) ON DELETE CASCADE,
    target_subagent VARCHAR(64) NOT NULL REFERENCES subagent_registry(id) ON DELETE CASCADE,
    workspace_id VARCHAR(64) NOT NULL DEFAULT 'default',
    handoff_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    npmi_coactivation DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    success_lift DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    latency_coupling DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    cost_share DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    composite_weight DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    polarity VARCHAR(16) NOT NULL DEFAULT 'neutral',
    sample_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_subagent, target_subagent, workspace_id),
    CONSTRAINT ck_correlation_polarity CHECK (polarity IN ('positive', 'negative', 'neutral'))
);

CREATE INDEX IF NOT EXISTS idx_corr_source_ws ON correlation_edges(source_subagent, workspace_id);
CREATE INDEX IF NOT EXISTS idx_corr_target_ws ON correlation_edges(target_subagent, workspace_id);
CREATE INDEX IF NOT EXISTS idx_corr_composite_weight ON correlation_edges(workspace_id, composite_weight DESC);

-- 7. TEMPORAL MEMORY FACTS (Bi-temporal)
CREATE TABLE IF NOT EXISTS temporal_memory_facts (
    fact_id VARCHAR(64) PRIMARY KEY,
    subject VARCHAR(128) NOT NULL,
    predicate VARCHAR(64) NOT NULL,
    object TEXT NOT NULL,
    valid_at TIMESTAMP WITH TIME ZONE NOT NULL,
    invalid_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expired_at TIMESTAMP WITH TIME ZONE,
    episode_run_id VARCHAR(64) NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    pii_redacted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_temporal_subject_predicate ON temporal_memory_facts(subject, predicate);
CREATE INDEX IF NOT EXISTS idx_temporal_validity_window ON temporal_memory_facts(valid_at, invalid_at);
CREATE INDEX IF NOT EXISTS idx_temporal_episode_run ON temporal_memory_facts(episode_run_id);

-- 8. AUDIT LOG (Append-only Cryptographic Hash Chain)
CREATE TABLE IF NOT EXISTS audit_log (
    log_id BIGINT PRIMARY KEY, -- Pada SQLite: INTEGER PRIMARY KEY AUTOINCREMENT
    actor VARCHAR(64) NOT NULL,
    action VARCHAR(64) NOT NULL,
    scope VARCHAR(128) NOT NULL,
    args_hash VARCHAR(64) NOT NULL,
    prev_hash VARCHAR(64) NOT NULL,
    curr_hash VARCHAR(64) NOT NULL UNIQUE,
    result_status VARCHAR(16) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_audit_result_status CHECK (result_status IN ('success', 'denied', 'error'))
);

CREATE INDEX IF NOT EXISTS idx_audit_actor_created ON audit_log(actor, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_prev_hash ON audit_log(prev_hash);
CREATE INDEX IF NOT EXISTS idx_audit_scope_action ON audit_log(scope, action);

-- 9. HITL INBOX
CREATE TABLE IF NOT EXISTS hitl_inbox (
    interrupt_id VARCHAR(64) PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    subagent_id VARCHAR(64) NOT NULL REFERENCES subagent_registry(id) ON DELETE CASCADE,
    reason VARCHAR(64) NOT NULL,
    state_diff JSON NOT NULL DEFAULT '{}',
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    approver VARCHAR(64),
    decision JSON,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT ck_hitl_status CHECK (status IN ('pending', 'approved', 'rejected', 'timed_out', 'cancelled')),
    CONSTRAINT ck_hitl_no_self_approval CHECK (approver IS NULL OR approver != subagent_id)
);

CREATE INDEX IF NOT EXISTS idx_hitl_run_id ON hitl_inbox(run_id);
CREATE INDEX IF NOT EXISTS idx_hitl_status_created ON hitl_inbox(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hitl_subagent ON hitl_inbox(subagent_id);
