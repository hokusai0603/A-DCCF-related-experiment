"""Producer -> A-DCCF byte cost (PREREGISTRATION 5.1, cost/sim_params.json).

bytes(notification) = a + sum over reports in it of (r + n_stat * s)
"""
import json
from dataclasses import dataclass
from pathlib import Path

PARAMS_PATH = Path(__file__).resolve().parent.parent / "cost" / "sim_params.json"


@dataclass(frozen=True)
class CostModel:
    a: float
    r: float
    s: float
    n_stat_raw: int = 10
    b_raw: float = 488.93
    label: str = "main"

    @classmethod
    def load(cls, variant="main", path=PARAMS_PATH):
        p = json.loads(Path(path).read_text())
        a = p["a"] if variant == "main" else p["a_sensitivity"]
        return cls(a=a, r=p["r"], s=p["s"], n_stat_raw=p["n_stat_raw"], b_raw=p["b_raw"],
                   label=variant)

    def report_bytes(self, n_stat):
        # A raw measurement (n_stat = 10) costs the measured b_raw = 488.93 B (PREREGISTRATION 5.1:
        # raw notification = 556.7 + 488.93 = 1,045.6 B). r and s are rounded in the table, so
        # r + 10 s = 489.0; using b_raw keeps B0/B1 exactly at the preregistered value.
        if n_stat == self.n_stat_raw:
            return self.b_raw
        return self.r + n_stat * self.s

    def bytes(self, n_notifications, n_reports, n_stat):
        """Total bytes for n_notifications carrying n_reports reports of n_stat statistics."""
        return n_notifications * self.a + n_reports * self.report_bytes(n_stat)

    @property
    def raw_notification_bytes(self):
        return self.a + self.report_bytes(self.n_stat_raw)


def load_all():
    return {"main": CostModel.load("main"), "sensitivity": CostModel.load("sensitivity")}
