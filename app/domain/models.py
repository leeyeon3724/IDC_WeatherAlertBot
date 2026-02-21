from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1


@dataclass(frozen=True)
class AlertEvent:
    area_code: str
    area_name: str
    warn_var: str
    warn_stress: str
    command: str
    cancel: str
    start_time: str | None
    end_time: str | None
    stn_id: str
    tm_fc: str
    tm_seq: str

    @property
    def event_id(self) -> str:
        if self.stn_id and self.tm_fc and self.tm_seq:
            # Include area + warning dimensions so same bulletin metadata does not collide
            # across different regions or warning categories.
            return (
                f"event:{self.stn_id}:{self.tm_fc}:{self.tm_seq}:"
                f"{self.area_code}:{self.warn_var}:{self.warn_stress}:"
                f"{self.command}:{self.cancel}"
            )

        fallback_source = "|".join(
            [
                self.area_code,
                self.area_name,
                self.warn_var,
                self.warn_stress,
                self.command,
                self.cancel,
                self.start_time or "",
                self.end_time or "",
                self.stn_id,
                self.tm_fc,
                self.tm_seq,
            ]
        )
        digest = sha1(fallback_source.encode("utf-8")).hexdigest()[:20]
        return f"fallback:{digest}"

    def validate_report_params(self) -> tuple[bool, str | None]:
        fields = [self.stn_id, self.tm_fc, self.tm_seq]
        has_any = any(fields)
        has_all = all(fields)

        if has_any and not has_all:
            return False, "incomplete_report_params"
        if not has_all:
            return True, None
        if len(self.tm_fc) != 12 or not self.tm_fc.isdigit():
            return False, "invalid_tm_fc"
        if not self.tm_seq.isdigit():
            return False, "invalid_tm_seq"
        return True, None

    @property
    def report_url(self) -> str | None:
        is_valid, _ = self.validate_report_params()
        if not is_valid:
            return None
        if not (self.stn_id and self.tm_fc and self.tm_seq):
            return None
        date_str = ""
        if len(self.tm_fc) == 12:
            date_str = f"{self.tm_fc[0:4]}-{self.tm_fc[4:6]}-{self.tm_fc[6:8]}"
        return (
            "https://www.weather.go.kr/w/special-report/list.do"
            f"?prevStn={self.stn_id}"
            "&prevKind=met"
            "&prevCmtCd="
            f"&stn={self.stn_id}"
            "&kind=met"
            f"&date={date_str}"
            f"&reportId=met%3A{self.tm_fc}%3A{self.tm_seq}"
        )


@dataclass(frozen=True)
class AlertNotification:
    event_id: str
    area_code: str
    message: str
    report_url: str | None
    url_validation_error: str | None = None
