"""Decision engine — multi-agent voting with quorum, escalation, and confidence scoring.

Implements weighted-majority, unanimous, and quorum strategies for
multi-agent incident resolution decisions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from governance_api.models.decision import AgentVote, Decision
from governance_api.models.incident import IncidentSeverity

logger = logging.getLogger("uc3.decision_engine")

# Confidence threshold above which auto-approval is allowed
AUTO_APPROVE_THRESHOLD = float(__import__("os").environ.get("AUTO_APPROVE_CONFIDENCE_THRESHOLD", "0.95"))


class DecisionEngine:
    """Evaluates agent votes and produces a resolution decision."""

    def evaluate(
        self,
        incident_id: str,
        votes: list[AgentVote],
        severity: IncidentSeverity,
        strategy: str = "weighted_majority",
    ) -> Decision:
        """Run the voting strategy and return a Decision."""
        if not votes:
            return Decision(
                incident_id=incident_id,
                outcome="escalate",
                confidence=0.0,
                strategy=strategy,
                votes=[],
                requires_approval=True,
                decided_at=datetime.now(timezone.utc),
                reasoning="No agent votes received — escalating to human.",
            )

        if strategy == "unanimous":
            return self._unanimous(incident_id, votes, severity)
        elif strategy == "quorum":
            return self._quorum(incident_id, votes, severity)
        else:
            return self._weighted_majority(incident_id, votes, severity)

    def _weighted_majority(
        self, incident_id: str, votes: list[AgentVote], severity: IncidentSeverity,
    ) -> Decision:
        """Weighted majority — each vote's weight is its confidence score."""
        recommendations: dict[str, float] = {}
        for v in votes:
            recommendations[v.recommendation] = (
                recommendations.get(v.recommendation, 0.0) + v.confidence
            )

        total_weight = sum(v.confidence for v in votes)
        best = max(recommendations, key=recommendations.get)  # type: ignore[arg-type]
        confidence = recommendations[best] / total_weight if total_weight > 0 else 0.0

        requires_approval = self._needs_approval(confidence, severity)
        reasoning = (
            f"Weighted majority: '{best}' with {confidence:.0%} weighted support "
            f"from {len(votes)} agents. "
            + ("Auto-approved (high confidence)." if not requires_approval else "Requires human approval.")
        )

        logger.info("Decision for %s: %s (confidence=%.2f, approval=%s)", incident_id, best, confidence, requires_approval)
        return Decision(
            incident_id=incident_id,
            outcome=best,
            confidence=round(confidence, 3),
            strategy="weighted_majority",
            votes=votes,
            requires_approval=requires_approval,
            decided_at=datetime.now(timezone.utc),
            reasoning=reasoning,
        )

    def _unanimous(
        self, incident_id: str, votes: list[AgentVote], severity: IncidentSeverity,
    ) -> Decision:
        """Unanimous — all agents must agree."""
        recommendations = {v.recommendation for v in votes}
        if len(recommendations) == 1:
            outcome = recommendations.pop()
            avg_conf = sum(v.confidence for v in votes) / len(votes)
            requires_approval = self._needs_approval(avg_conf, severity)
            return Decision(
                incident_id=incident_id,
                outcome=outcome,
                confidence=round(avg_conf, 3),
                strategy="unanimous",
                votes=votes,
                requires_approval=requires_approval,
                decided_at=datetime.now(timezone.utc),
                reasoning=f"Unanimous agreement: '{outcome}' ({len(votes)} agents, avg confidence {avg_conf:.0%}).",
            )
        else:
            return Decision(
                incident_id=incident_id,
                outcome="escalate",
                confidence=0.0,
                strategy="unanimous",
                votes=votes,
                requires_approval=True,
                decided_at=datetime.now(timezone.utc),
                reasoning=f"No unanimity — agents disagreed: {recommendations}. Escalating.",
            )

    def _quorum(
        self, incident_id: str, votes: list[AgentVote], severity: IncidentSeverity,
    ) -> Decision:
        """Quorum — need >50% of agents to agree."""
        recommendations: dict[str, int] = {}
        for v in votes:
            recommendations[v.recommendation] = recommendations.get(v.recommendation, 0) + 1

        best = max(recommendations, key=recommendations.get)  # type: ignore[arg-type]
        count = recommendations[best]
        quorum_met = count > len(votes) / 2

        if quorum_met:
            avg_conf = sum(v.confidence for v in votes if v.recommendation == best) / count
            requires_approval = self._needs_approval(avg_conf, severity)
            return Decision(
                incident_id=incident_id,
                outcome=best,
                confidence=round(avg_conf, 3),
                strategy="quorum",
                votes=votes,
                requires_approval=requires_approval,
                decided_at=datetime.now(timezone.utc),
                reasoning=f"Quorum reached: '{best}' ({count}/{len(votes)} agents).",
            )
        else:
            return Decision(
                incident_id=incident_id,
                outcome="escalate",
                confidence=0.0,
                strategy="quorum",
                votes=votes,
                requires_approval=True,
                decided_at=datetime.now(timezone.utc),
                reasoning=f"No quorum — no recommendation received >50% votes. Escalating.",
            )

    def _needs_approval(self, confidence: float, severity: IncidentSeverity) -> bool:
        """Determine if human approval is required."""
        # P1/P2 always need approval regardless of confidence
        if severity in (IncidentSeverity.P1, IncidentSeverity.P2):
            return True
        # High-confidence P3/P4 can be auto-approved
        return confidence < AUTO_APPROVE_THRESHOLD
