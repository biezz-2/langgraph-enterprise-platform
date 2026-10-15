import { createClient } from '@supabase/supabase-js'

export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://supabase-self-hosted.biezz.my.id'
export const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || ''
export const SUPABASE_SCHEMA = process.env.NEXT_PUBLIC_SUPABASE_SCHEMA || 'langgraph'

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  db: {
    schema: SUPABASE_SCHEMA,
  },
  auth: {
    persistSession: false,
  },
})

export type Database = {
  langgraph: {
    Tables: {
      subagent_registry: {
        Row: {
          id: string
          role: string
          name: string
          pod: string
          capabilities: string
          input_schema: string
          output_schema: string
          tool_grants: string
          model_policy: string
          budget_config: string
          memory_scope: string
          trust_level: string
          is_active: number
          version: string
          created_at?: string
          updated_at?: string
        }
        Insert: Partial<Database['langgraph']['Tables']['subagent_registry']['Row']>
        Update: Partial<Database['langgraph']['Tables']['subagent_registry']['Row']>
      }
      threads: {
        Row: {
          thread_id: string
          title: string
          metadata_json: Record<string, unknown> | string
          created_at?: string
          updated_at?: string
        }
        Insert: Partial<Database['langgraph']['Tables']['threads']['Row']>
        Update: Partial<Database['langgraph']['Tables']['threads']['Row']>
      }
      runs: {
        Row: {
          run_id: string
          thread_id: string
          status: string
          objective: string
          current_subagent: string | null
          context_packet_json: Record<string, unknown> | string | null
          budget_allocated_json: Record<string, unknown> | string | null
          budget_spent_json: Record<string, unknown> | string | null
          consecutive_failures: number
          circuit_open: number
          created_at?: string
          updated_at?: string
        }
        Insert: Partial<Database['langgraph']['Tables']['runs']['Row']>
        Update: Partial<Database['langgraph']['Tables']['runs']['Row']>
      }
      correlation_edges: {
        Row: {
          source_subagent: string
          target_subagent: string
          handoff_rate: number
          npmi_coactivation: number
          success_lift: number
          latency_coupling: number
          composite_weight: number
          polarity: string
          sample_count: number
          updated_at?: string
        }
        Insert: Partial<Database['langgraph']['Tables']['correlation_edges']['Row']>
        Update: Partial<Database['langgraph']['Tables']['correlation_edges']['Row']>
      }
      temporal_facts: {
        Row: {
          fact_id: string
          subject: string
          predicate: string
          object: string
          valid_at: string
          invalid_at: string | null
          created_at: string
          expired_at: string | null
          episode_run_id: string | null
          pii_redacted: number
        }
        Insert: Partial<Database['langgraph']['Tables']['temporal_facts']['Row']>
        Update: Partial<Database['langgraph']['Tables']['temporal_facts']['Row']>
      }
      audit_log: {
        Row: {
          log_id: string
          actor: string
          action: string
          scope: string
          args_hash: string
          prev_hash: string
          curr_hash: string
          result_status: string
          created_at?: string
        }
        Insert: Partial<Database['langgraph']['Tables']['audit_log']['Row']>
        Update: Partial<Database['langgraph']['Tables']['audit_log']['Row']>
      }
      kanban_boards: {
        Row: {
          id: string
          name: string
          created_at?: string | number
          updated_at?: string | number
        }
        Insert: Partial<Database['langgraph']['Tables']['kanban_boards']['Row']>
        Update: Partial<Database['langgraph']['Tables']['kanban_boards']['Row']>
      }
      kanban_columns: {
        Row: {
          id: string
          board_id: string
          name: string
          order_idx: number
        }
        Insert: Partial<Database['langgraph']['Tables']['kanban_columns']['Row']>
        Update: Partial<Database['langgraph']['Tables']['kanban_columns']['Row']>
      }
      kanban_cards: {
        Row: {
          id: string
          column_id: string
          title: string
          description: string
          priority: string
          assigned_to: string | null
          metadata_json: Record<string, unknown> | string
          created_at?: string | number
          updated_at?: string | number
        }
        Insert: Partial<Database['langgraph']['Tables']['kanban_cards']['Row']>
        Update: Partial<Database['langgraph']['Tables']['kanban_cards']['Row']>
      }
      matrix_config: {
        Row: {
          id: string
          name: string
          description: string
          alpha: number
          beta: number
          gamma: number
          n_min: number
          enabled: number
          created_at?: string | number
        }
        Insert: Partial<Database['langgraph']['Tables']['matrix_config']['Row']>
        Update: Partial<Database['langgraph']['Tables']['matrix_config']['Row']>
      }
    }
  }
}
