import json
import hashlib
from typing import Dict, List, Any, Optional, Tuple
from packages.core.models import BudgetEnvelope, ContextPacket

class InheritedBudgetManager:
    DAILY_HARD_STOP_USD = 15.0

    def __init__(self, daily_spent_usd: float = 0.0):
        self.daily_spent_usd = daily_spent_usd

    def check_daily_limit(self, requested_usd: float) -> bool:
        return (self.daily_spent_usd + requested_usd) <= self.DAILY_HARD_STOP_USD

    def validate_delegation_budget(self, parent_budget: BudgetEnvelope, child_tokens: int, child_usd: float) -> BudgetEnvelope:
        remaining_tokens = max(0, parent_budget.max_tokens - parent_budget.spent_tokens)
        remaining_usd = max(0.0, parent_budget.max_usd - parent_budget.spent_usd)

        if child_tokens > remaining_tokens or child_usd > remaining_usd:
            raise ValueError(
                f"Budget violation: Anak meminta ({child_tokens} tok, ${child_usd}) "
                f"melebihi sisa induk ({remaining_tokens} tok, ${remaining_usd:.2f})"
            )

        if not self.check_daily_limit(child_usd):
            raise ValueError(f"Daily hard stop reached: akumulasi ${self.daily_spent_usd:.2f} + ${child_usd:.2f} > ${self.DAILY_HARD_STOP_USD}")

        return parent_budget.spawn_child_budget(child_tokens, child_usd)

class CircuitBreaker:
    MAX_CONSECUTIVE_FAILURES = 3

    def __init__(self):
        self.failure_counts: Dict[str, int] = {}
        self.open_circuits: Dict[str, bool] = {}

    def record_success(self, subagent_id: str):
        self.failure_counts[subagent_id] = 0

    def record_failure(self, subagent_id: str) -> bool:
        count = self.failure_counts.get(subagent_id, 0) + 1
        self.failure_counts[subagent_id] = count
        if count >= self.MAX_CONSECUTIVE_FAILURES:
            self.open_circuits[subagent_id] = True
            return True  # Circuit tripped
        return False

    def is_open(self, subagent_id: str) -> bool:
        return self.open_circuits.get(subagent_id, False)

    def reset(self, subagent_id: str):
        self.failure_counts[subagent_id] = 0
        self.open_circuits[subagent_id] = False

class LoopDetector:
    THRESHOLD = 3
    WINDOW_SIZE = 10

    def __init__(self):
        self.history: List[str] = []

    def compute_state_hash(self, subagent_id: str, tool_name: str, args: Any, state_snapshot: Any) -> str:
        canonical_args = json.dumps(args, sort_keys=True) if args else ""
        canonical_state = json.dumps(state_snapshot, sort_keys=True) if state_snapshot else ""
        payload = f"{subagent_id}:{tool_name}:{canonical_args}:{canonical_state}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def record_and_check(self, state_hash: str) -> bool:
        self.history.append(state_hash)
        if len(self.history) > self.WINDOW_SIZE:
            self.history.pop(0)

        occurrences = self.history.count(state_hash)
        return occurrences >= self.THRESHOLD

class SecurityToolGuard:
    INJECTION_PATTERNS = [
        "ignore previous instructions",
        "system prompt override",
        "delete from ",
        "drop table ",
        "rm -rf /",
        "cat /etc/shadow",
        "export AWS_SECRET_ACCESS_KEY"
    ]

    @classmethod
    def sanitize_input(cls, text: str) -> Tuple[bool, Optional[str]]:
        lower = text.lower()
        for p in cls.INJECTION_PATTERNS:
            if p in lower:
                return False, f"Potensi prompt injection terdeteksi: '{p}'"
        return True, None

    @classmethod
    def redact_secrets(cls, data: Any) -> Any:
        if isinstance(data, str):
            # Redact actual secret tokens or keys
            if data.startswith("sk-") or "password=" in data.lower() or "secret_key" in data.lower():
                return "[REDACTED_SECRET]"
            return data
        elif isinstance(data, dict):
            return {k: ("[REDACTED_SECRET]" if "secret" in k.lower() or "key" in k.lower() or "password" in k.lower() else cls.redact_secrets(v)) for k, v in data.items()}
        elif isinstance(data, list):
            return [cls.redact_secrets(v) for v in data]
        return data

    @classmethod
    def validate_subagent_tool_access(cls, subagent_id: str, requested_tool: str, tool_args: Dict[str, Any]) -> Tuple[bool, str]:
        # PR-SEC-02: Clio tidak memiliki akses Admin MCP
        if subagent_id == "clio" and requested_tool.startswith("admin:"):
            return False, "Akses ditolak: Clio (untrusted web research) dilarang mengakses Admin MCP"

        # PR-SEC-03: Vulcan tidak dapat self-promote ke prod
        if subagent_id == "vulcan" and requested_tool == "graphs:promote_prod":
            return False, "Akses ditolak: Vulcan tidak diizinkan self-promote. Perlu persetujuan manusia (HITL)"

        # PR-SEC-04: Themis tidak pernah menerima nilai secret, hanya secret_ref
        if subagent_id == "themis":
            for k, v in tool_args.items():
                if "secret_val" in k or ("secret" in k and not str(v).startswith("secret://")):
                    return False, "Akses ditolak: Themis hanya boleh menerima referensi 'secret://', bukan raw secret value"

        return True, "OK"
