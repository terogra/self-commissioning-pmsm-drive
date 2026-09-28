"""Compose electrical and mechanical stages without hidden plant information."""

from dataclasses import dataclass, replace

import numpy as np

from src.commissioning import CommissioningRejectedError, CommissioningResult
from src.commissioning_quality import CommissioningQuality
from src.mechanical_identification import (
    MechanicalEstimate, MechanicalQualityPolicy, assess_mechanical, estimate_mechanical_parameters,
)


@dataclass(frozen=True)
class MechanicalCommissioningResult:
    estimate: MechanicalEstimate | None
    quality: CommissioningQuality


@dataclass(frozen=True)
class FullCommissioningResult:
    electrical: CommissioningResult
    mechanical: MechanicalCommissioningResult

    @property
    def quality(self):
        e, m = self.electrical.quality, self.mechanical.quality
        return CommissioningQuality(e.accepted and m.accepted,
                                    e.rejection_reasons + m.rejection_reasons,
                                    e.checks + m.checks, e.estimator_failure or m.estimator_failure)

    def retuned_controller_parameters(self, prior):
        if not self.quality.accepted or self.mechanical.estimate is None:
            raise CommissioningRejectedError(self.quality)
        electrical_params = self.electrical.retuned_controller_parameters(prior)
        return replace(electrical_params, J=self.mechanical.estimate.J, B=self.mechanical.estimate.B)


def complete_commissioning(electrical_result, mechanical_data, policy=MechanicalQualityPolicy()):
    """Append measured J/B identification; full retuning requires both gates.

    On failure the full result cannot update any controller field. Users may
    explicitly retain/use the accepted electrical-only result separately.
    """
    estimate = None
    if not electrical_result.quality.accepted:
        quality = CommissioningQuality(False, ("mechanical.electrical_not_accepted",))
    else:
        try:
            estimate = estimate_mechanical_parameters(
                mechanical_data, electrical_result.electrical, electrical_result.flux,
                electrical_result.pole_pairs,
            )
            quality = assess_mechanical(estimate, policy)
        except (ValueError, FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
            quality = CommissioningQuality(False, (str(exc),), estimator_failure=str(exc))
    return FullCommissioningResult(electrical_result, MechanicalCommissioningResult(estimate, quality))
