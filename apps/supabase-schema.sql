-- ============================================================================
-- LangGraph Platform (LGP v2.0) - Supabase Self-Hosted Isolated Schema
-- Schema: langgraph
-- Instance: https://supabase-self-hosted.biezz.my.id
-- ============================================================================

-- 1. Setup Extension & Dedicated Schema Isolation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE SCHEMA IF NOT EXISTS langgraph;
SET search_path TO langgraph, public;

-- ============================================================================
-- 2. Core Tables Definition
-- ============================================================================

-- Subagent Registry
CREATE TABLE IF NOT EXISTS langgraph.subagent_registry (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    name TEXT NOT NULL,
    pod TEXT NOT NULL,
    capabilities TEXT NOT NULL, -- JSON formatted array/object
    input_schema TEXT NOT NULL, -- JSON Schema
    output_schema TEXT NOT NULL, -- JSON Schema
    tool_grants TEXT NOT NULL, -- JSON formatted array
    model_policy TEXT NOT NULL,
    budget_config TEXT NOT NULL, -- JSON formatted envelope
    memory_scope TEXT NOT NULL,
    trust_level TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    version TEXT NOT NULL DEFAULT '2.0.0',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Threads
CREATE TABLE IF NOT EXISTS langgraph.threads (
    thread_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    metadata_json JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Runs
CREATE TABLE IF NOT EXISTS langgraph.runs (
    run_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    status TEXT NOT NULL, -- queued, running, interrupted, completed, failed
    objective TEXT NOT NULL,
    current_subagent TEXT,
    context_packet_json JSONB,
    budget_allocated_json JSONB,
    budget_spent_json JSONB,
    consecutive_failures INTEGER DEFAULT 0,
    circuit_open INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (thread_id) REFERENCES langgraph.threads(thread_id) ON DELETE CASCADE
);

-- Checkpoints
CREATE TABLE IF NOT EXISTS langgraph.checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step INTEGER NOT NULL,
    state_hash TEXT NOT NULL,
    state_data_json JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (run_id) REFERENCES langgraph.runs(run_id) ON DELETE CASCADE
);

-- Telemetry Events
CREATE TABLE IF NOT EXISTS langgraph.telemetry_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    subagent_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json JSONB DEFAULT '{}'::jsonb,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,
    latency_ms REAL DEFAULT 0.0,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (run_id) REFERENCES langgraph.runs(run_id) ON DELETE CASCADE
);

-- Correlation Edges
CREATE TABLE IF NOT EXISTS langgraph.correlation_edges (
    source_subagent TEXT NOT NULL,
    target_subagent TEXT NOT NULL,
    handoff_rate REAL DEFAULT 0.0,
    npmi_coactivation REAL DEFAULT 0.0,
    success_lift REAL DEFAULT 0.0,
    latency_coupling REAL DEFAULT 0.0,
    composite_weight REAL DEFAULT 0.0,
    polarity TEXT DEFAULT 'neutral',
    sample_count INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (source_subagent, target_subagent)
);

-- Temporal Facts (Bi-temporal Memory L2)
CREATE TABLE IF NOT EXISTS langgraph.temporal_facts (
    fact_id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    valid_at TIMESTAMPTZ NOT NULL,
    invalid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    expired_at TIMESTAMPTZ,
    episode_run_id TEXT,
    pii_redacted INTEGER DEFAULT 1
);

-- Audit Log (Cryptographically chained)
CREATE TABLE IF NOT EXISTS langgraph.audit_log (
    log_id TEXT PRIMARY KEY,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    scope TEXT NOT NULL,
    args_hash TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    curr_hash TEXT NOT NULL,
    result_status TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- HITL Inbox
CREATE TABLE IF NOT EXISTS langgraph.hitl_inbox (
    interrupt_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    subagent_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    state_diff_json JSONB DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending', -- pending, approved, rejected
    approver TEXT,
    decision TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    FOREIGN KEY (run_id) REFERENCES langgraph.runs(run_id) ON DELETE CASCADE
);

-- Correlation Settings
CREATE TABLE IF NOT EXISTS langgraph.correlation_settings (
    workspace_id TEXT PRIMARY KEY DEFAULT 'default',
    alpha REAL NOT NULL DEFAULT 0.4,
    beta REAL NOT NULL DEFAULT 0.4,
    gamma REAL NOT NULL DEFAULT 0.2,
    n_min INTEGER NOT NULL DEFAULT 50,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Kanban Boards
CREATE TABLE IF NOT EXISTS langgraph.kanban_boards (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Kanban Columns
CREATE TABLE IF NOT EXISTS langgraph.kanban_columns (
    id TEXT PRIMARY KEY,
    board_id TEXT NOT NULL,
    name TEXT NOT NULL,
    order_idx INTEGER NOT NULL,
    FOREIGN KEY (board_id) REFERENCES langgraph.kanban_boards(id) ON DELETE CASCADE
);

-- Kanban Cards
CREATE TABLE IF NOT EXISTS langgraph.kanban_cards (
    id TEXT PRIMARY KEY,
    column_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    priority TEXT DEFAULT 'medium',
    assigned_to TEXT,
    metadata_json JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (column_id) REFERENCES langgraph.kanban_columns(id) ON DELETE CASCADE
);

-- Matrix Configuration
CREATE TABLE IF NOT EXISTS langgraph.matrix_config (
    id TEXT PRIMARY KEY DEFAULT 'default',
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    alpha REAL NOT NULL DEFAULT 0.4,
    beta REAL NOT NULL DEFAULT 0.4,
    gamma REAL NOT NULL DEFAULT 0.2,
    n_min INTEGER NOT NULL DEFAULT 50,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 3. Indexes for Query Performance
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_telemetry_run ON langgraph.telemetry_events(run_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_agent ON langgraph.telemetry_events(subagent_id);
CREATE INDEX IF NOT EXISTS idx_temporal_subject ON langgraph.temporal_facts(subject);
CREATE INDEX IF NOT EXISTS idx_temporal_validity ON langgraph.temporal_facts(valid_at, invalid_at);
CREATE INDEX IF NOT EXISTS idx_kanban_cards_column ON langgraph.kanban_cards(column_id);
CREATE INDEX IF NOT EXISTS idx_kanban_columns_board ON langgraph.kanban_columns(board_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON langgraph.runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_thread ON langgraph.runs(thread_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON langgraph.audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_checkpoints_run ON langgraph.checkpoints(run_id);

-- ============================================================================
-- 4. Triggers for Automatic updated_at
-- ============================================================================

CREATE OR REPLACE FUNCTION langgraph.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_subagent_registry_updated_at ON langgraph.subagent_registry;
CREATE TRIGGER update_subagent_registry_updated_at BEFORE UPDATE ON langgraph.subagent_registry
    FOR EACH ROW EXECUTE FUNCTION langgraph.update_updated_at_column();

DROP TRIGGER IF EXISTS update_threads_updated_at ON langgraph.threads;
CREATE TRIGGER update_threads_updated_at BEFORE UPDATE ON langgraph.threads
    FOR EACH ROW EXECUTE FUNCTION langgraph.update_updated_at_column();

DROP TRIGGER IF EXISTS update_runs_updated_at ON langgraph.runs;
CREATE TRIGGER update_runs_updated_at BEFORE UPDATE ON langgraph.runs
    FOR EACH ROW EXECUTE FUNCTION langgraph.update_updated_at_column();

DROP TRIGGER IF EXISTS update_kanban_boards_updated_at ON langgraph.kanban_boards;
CREATE TRIGGER update_kanban_boards_updated_at BEFORE UPDATE ON langgraph.kanban_boards
    FOR EACH ROW EXECUTE FUNCTION langgraph.update_updated_at_column();

DROP TRIGGER IF EXISTS update_kanban_cards_updated_at ON langgraph.kanban_cards;
CREATE TRIGGER update_kanban_cards_updated_at BEFORE UPDATE ON langgraph.kanban_cards
    FOR EACH ROW EXECUTE FUNCTION langgraph.update_updated_at_column();

-- ============================================================================
-- 5. Row Level Security (RLS) Policies
-- ============================================================================

ALTER TABLE langgraph.subagent_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph.threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph.runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph.checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph.telemetry_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph.correlation_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph.temporal_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph.audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph.hitl_inbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph.correlation_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph.kanban_boards ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph.kanban_columns ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph.kanban_cards ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph.matrix_config ENABLE ROW LEVEL SECURITY;

-- Service role full access policies
DO $$
DECLARE
    tbl text;
    tables text[] := ARRAY[
        'subagent_registry', 'threads', 'runs', 'checkpoints', 'telemetry_events',
        'correlation_edges', 'temporal_facts', 'audit_log', 'hitl_inbox',
        'correlation_settings', 'kanban_boards', 'kanban_columns', 'kanban_cards',
        'matrix_config'
    ];
BEGIN
    FOREACH tbl IN ARRAY tables LOOP
        EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON langgraph.%I;', tbl);
        EXECUTE format('CREATE POLICY "Service role full access" ON langgraph.%I FOR ALL USING (auth.role() = ''service_role'') WITH CHECK (auth.role() = ''service_role'');', tbl);

        EXECUTE format('DROP POLICY IF EXISTS "Anon read access" ON langgraph.%I;', tbl);
        EXECUTE format('CREATE POLICY "Anon read access" ON langgraph.%I FOR SELECT USING (true);', tbl);
    END LOOP;
END $$;

-- ============================================================================
-- 6. Schema Grants and Permissions
-- ============================================================================

-- Schema usage and administration
GRANT ALL ON SCHEMA langgraph TO postgres, service_role;
GRANT USAGE ON SCHEMA langgraph TO anon, authenticated;

-- Table permissions
GRANT ALL ON ALL TABLES IN SCHEMA langgraph TO postgres, service_role;
GRANT SELECT ON ALL TABLES IN SCHEMA langgraph TO anon, authenticated;

-- Sequence permissions
GRANT ALL ON ALL SEQUENCES IN SCHEMA langgraph TO postgres, service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA langgraph TO anon, authenticated;

-- Routine/Function permissions
GRANT ALL ON ALL ROUTINES IN SCHEMA langgraph TO postgres, service_role;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA langgraph TO anon, authenticated;

-- Future tables/sequences created in schema
ALTER DEFAULT PRIVILEGES IN SCHEMA langgraph GRANT ALL ON TABLES TO postgres, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA langgraph GRANT SELECT ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA langgraph GRANT ALL ON SEQUENCES TO postgres, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA langgraph GRANT USAGE, SELECT ON SEQUENCES TO anon, authenticated;
