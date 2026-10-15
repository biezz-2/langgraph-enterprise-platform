import re
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Union
from packages.core.models import TemporalFact


def _to_float(v: Union[float, int, datetime, str, None]) -> Optional[float]:
    """Normalize datetime/str/float to epoch float for comparison."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, datetime):
        return v.timestamp()
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v).timestamp()
        except ValueError:
            return float(v)
    return float(v)

class TemporalMemoryStore:
    EMAIL_PATTERN = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+")
    PHONE_PATTERN = re.compile(r"\b(?:\+?\d{1,3}[- ]?)?\(?\d{3}\)?[- ]?\d{3}[- ]?\d{4}\b")
    NIK_PATTERN = re.compile(r"\b\d{16}\b")  # Indonesian NIK regex

    def __init__(self):
        pass

    @classmethod
    def redact_pii(cls, text: str) -> str:
        text = cls.EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
        text = cls.PHONE_PATTERN.sub("[REDACTED_PHONE]", text)
        text = cls.NIK_PATTERN.sub("[REDACTED_NIK]", text)
        return text

    @classmethod
    def create_fact(
        cls,
        subject: str,
        predicate: str,
        obj: str,
        valid_at: Optional[float] = None,
        invalid_at: Optional[float] = None,
        episode_run_id: Optional[str] = None
    ) -> TemporalFact:
        now = time.time()
        redacted_obj = cls.redact_pii(obj)
        return TemporalFact(
            subject=subject,
            predicate=predicate.upper(),
            object=redacted_obj,
            valid_at=valid_at if valid_at is not None else now,
            invalid_at=invalid_at,
            created_at=now,
            expired_at=now + (86400 * 365),  # 1 year retention
            episode_run_id=episode_run_id,
            pii_redacted=True
        )

    @classmethod
    def filter_bitemporal(
        cls,
        facts: List[TemporalFact],
        as_of_valid_time: Optional[float] = None,
        as_of_record_time: Optional[float] = None
    ) -> List[TemporalFact]:
        results = []
        tv = as_of_valid_time if as_of_valid_time is not None else time.time()
        tk = as_of_record_time if as_of_record_time is not None else time.time()

        for f in facts:
            created = _to_float(f.created_at)
            expired = _to_float(f.expired_at)
            valid = _to_float(f.valid_at)
            invalid = _to_float(f.invalid_at)

            # Record time check: was this fact known to the system at tk?
            if created is not None and created > tk:
                continue
            if expired is not None and expired <= tk:
                continue

            # Valid time check: was this fact valid in reality at tv?
            if valid is not None and valid > tv:
                continue
            if invalid is not None and invalid <= tv:
                continue

            results.append(f)
        return results

    @classmethod
    def to_agents_markdown(cls, facts: List[TemporalFact]) -> str:
        """Render active bi-temporal facts into AGENTS.md format."""
        if not facts:
            return "# AGENTS MEMORY\n\n_Belum ada fakta aktif._\n"
        
        lines = ["# AGENTS MEMORY (Bi-Temporal Facts)", "", "| Subject | Predicate | Object | Valid Since | Run ID |", "|---|---|---|---|---|"]
        for f in facts:
            val_float = _to_float(f.valid_at)
            vt = datetime.fromtimestamp(val_float, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if val_float else "-"
            sub = f.subject.replace("|", "\\|")
            pred = f.predicate.replace("|", "\\|")
            obj = f.object.replace("|", "\\|")
            rid = (f.episode_run_id or "-").replace("|", "\\|")
            lines.append(f"| {sub} | {pred} | {obj} | {vt} | {rid} |")
        return "\n".join(lines) + "\n"

