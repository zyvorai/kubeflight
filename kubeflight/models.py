from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Any

SEVERITY_WEIGHT = {"info": 0, "low": 2, "medium": 6, "high": 14, "critical": 28}

@dataclass
class Finding:
    id: str
    severity: str
    category: str
    title: str
    resource: str
    evidence: str
    recommendation: str
    deterministic: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass
class ScheduleResult:
    workload: str
    replicas: int
    fitting_nodes: list[str] = field(default_factory=list)
    placements: list[str] = field(default_factory=list)
    unscheduled_replicas: int = 0
    reasons: dict[str, list[str]] = field(default_factory=dict)
    @property
    def schedulable(self) -> bool: return self.unscheduled_replicas == 0
    def to_dict(self) -> dict[str, Any]:
        d=asdict(self); d["schedulable"]=self.schedulable; return d

@dataclass
class Assessment:
    score: int
    decision: str
    resources: int
    findings: list[Finding]
    schedule: list[ScheduleResult]
    dependencies: dict[str, list[str]]
    changed: list[str]
    blast_radius: list[str]
    monthly_cost: float
    baseline_monthly_cost: float | None
    target_kubernetes: str
    summary: dict[str, int]
    limitations: list[str] = field(default_factory=list)
    def to_dict(self) -> dict[str, Any]:
        return {
            "score":self.score,"decision":self.decision,"resources":self.resources,
            "findings":[f.to_dict() for f in self.findings],"schedule":[s.to_dict() for s in self.schedule],
            "dependencies":self.dependencies,"changed":self.changed,"blast_radius":self.blast_radius,
            "monthly_cost":round(self.monthly_cost,2),
            "baseline_monthly_cost":None if self.baseline_monthly_cost is None else round(self.baseline_monthly_cost,2),
            "cost_delta":None if self.baseline_monthly_cost is None else round(self.monthly_cost-self.baseline_monthly_cost,2),
            "target_kubernetes":self.target_kubernetes,"summary":self.summary,"limitations":self.limitations,
        }
