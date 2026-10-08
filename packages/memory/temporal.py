import re
import time
from typing import List, Dict, Any, Optional
from packages.core.models import TemporalFact

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
            # Record time check: was this fact known to the system at tk?
            if f.created_at > tk:
                continue
            if f.expired_at and f.expired_at <= tk:
                continue

            # Valid time check: was this fact valid in reality at tv?
            if f.valid_at > tv:
                continue
            if f.invalid_at and f.invalid_at <= tv:
                continue

            results.append(f)
        return results
