import math
import time
from typing import Dict, List, Any, Optional, Tuple
from packages.core.models import CorrelationEdge

SUBAGENT_IDS = [
    "atlas", "clio", "vulcan", "athena", "hermes",
    "mnemosyne", "janus", "themis", "metron", "iris"
]

class CorrelationCalculator:
    ALPHA = 0.4  # NPMI weight
    BETA = 0.4   # Success lift weight
    GAMMA = 0.2  # Handoff rate weight
    N_MIN = 50   # Threshold for "data sedikit"

    def __init__(self, alpha: float = 0.4, beta: float = 0.4, gamma: float = 0.2):
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma

    def calculate_npmi(self, p_i: float, p_j: float, p_ij: float) -> float:
        if p_ij <= 0 or p_i <= 0 or p_j <= 0:
            return 0.0
        if p_ij >= 1.0:
            return 1.0 if (p_i >= 1.0 and p_j >= 1.0) else 0.0
        pmi = math.log(p_ij / (p_i * p_j))
        denom = -math.log(p_ij)
        if abs(denom) < 1e-9:
            return 1.0
        npmi = pmi / denom
        return max(-1.0, min(1.0, npmi))

    def compute_edge(
        self,
        source: str,
        target: str,
        handoffs: int,
        total_source_handoffs: int,
        co_activations: int,
        source_activations: int,
        target_activations: int,
        total_runs: int,
        co_successes: int,
        total_successes: int
    ) -> CorrelationEdge:
        if total_runs == 0:
            return CorrelationEdge(
                source_subagent=source,
                target_subagent=target,
                polarity="neutral",
                sample_count=0
            )

        # 1. Handoff Rate
        handoff_rate = (handoffs / total_source_handoffs) if total_source_handoffs > 0 else 0.0

        # 2. Co-activation NPMI
        p_i = source_activations / total_runs
        p_j = target_activations / total_runs
        p_ij = co_activations / total_runs
        npmi = self.calculate_npmi(p_i, p_j, p_ij)

        # 3. Success Lift
        baseline_success_rate = total_successes / total_runs if total_runs > 0 else 0.5
        co_success_rate = (co_successes / co_activations) if co_activations > 0 else baseline_success_rate
        success_lift = co_success_rate - baseline_success_rate

        # 4. Composite Weight
        composite = (self.alpha * npmi) + (self.beta * success_lift) + (self.gamma * handoff_rate)

        # 5. Polarity
        if composite > 0.05:
            polarity = "positive"
        elif composite < -0.05:
            polarity = "negative"
        else:
            polarity = "neutral"

        return CorrelationEdge(
            source_subagent=source,
            target_subagent=target,
            handoff_rate=round(handoff_rate, 4),
            npmi_coactivation=round(npmi, 4),
            success_lift=round(success_lift, 4),
            composite_weight=round(composite, 4),
            polarity=polarity,
            sample_count=co_activations,
            updated_at=time.time()
        )

    def generate_10x10_matrix(self, edges: List[CorrelationEdge]) -> Dict[str, Any]:
        edge_map = {(e.source_subagent, e.target_subagent): e for e in edges}
        matrix: List[List[Dict[str, Any]]] = []

        for src in SUBAGENT_IDS:
            row = []
            for tgt in SUBAGENT_IDS:
                if src == tgt:
                    row.append({
                        "source": src,
                        "target": tgt,
                        "weight": 1.0,
                        "polarity": "self",
                        "handoff_rate": 0.0,
                        "npmi": 1.0,
                        "sample_count": 0,
                        "low_data": False
                    })
                else:
                    edge = edge_map.get((src, tgt))
                    weight = edge.composite_weight if edge else 0.0
                    polarity = edge.polarity if edge else "neutral"
                    sample_count = edge.sample_count if edge else 0
                    row.append({
                        "source": src,
                        "target": tgt,
                        "weight": weight,
                        "polarity": polarity,
                        "handoff_rate": edge.handoff_rate if edge else 0.0,
                        "npmi": edge.npmi_coactivation if edge else 0.0,
                        "sample_count": sample_count,
                        "low_data": sample_count < self.N_MIN
                    })
            matrix.append(row)

        return {
            "subagents": SUBAGENT_IDS,
            "matrix": matrix,
            "alpha": self.alpha,
            "beta": self.beta,
            "gamma": self.gamma,
            "n_min": self.N_MIN
        }
