export type NeuronNodeType = "subagent" | "category" | "fact_entity" | "entity" | "hub" | "invalidated" | string;

export interface NeuronNode {
  id: string;
  label: string;
  type: NeuronNodeType;
  group?: string;
  color: string;
  size?: number;
  description?: string;
  status?: "active" | "invalid" | "pending" | string;
  icon?: string;
  role?: string;
  pod?: string;
  trust_level?: string;
  model_policy?: string;
  budget?: Record<string, unknown>;
  capabilities?: string[];
  subject?: string;
  predicate?: string;
  object?: string;
  valid_at?: string | number | null;
  invalid_at?: string | number | null;
  episode_run_id?: string;
  degree?: number;
  inDegree?: number;
  outDegree?: number;
  x?: number;
  y?: number;
  z?: number;
  vx?: number;
  vy?: number;
  vz?: number;
}

export interface NeuronLink {
  id?: string;
  source: string | NeuronNode;
  target: string | NeuronNode;
  type?: string;
  relation?: string;
  weight?: number;
  color?: string;
  predicate?: string;
  detail?: string;
  animated?: boolean;
}

export interface NeuronGraphData {
  nodes: NeuronNode[];
  links: NeuronLink[];
  engine?: string;
  style?: string;
  timestamp?: number;
  stats?: {
    total_nodes?: number;
    total_edges?: number;
    active_facts?: number;
    categories?: number;
  };
}

export interface ObsidianPhysicsConfig {
  repelForce: number; // charge strength: -50 to -800
  linkDistance: number; // link distance: 20 to 200
  centerGravity: number; // center force: 0.01 to 0.5
  particleSpeed: number; // directional particle speed: 0.001 to 0.02
  nodeSizeScale: number; // scaling factor: 0.5 to 2.0
  particleDensity: number; // particles per link: 0 to 6
}
