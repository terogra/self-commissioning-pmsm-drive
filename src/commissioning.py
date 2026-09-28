"""Combine electrical identification stages and update controller assumptions."""

from dataclasses import dataclass, replace
import numpy as np

from src.commissioning_quality import CommissioningQuality, QualityPolicy, assess_commissioning

from src.identification import (
    ElectricalEstimate,
    StandstillMeasurements,
    estimate_standstill_parameters,
)
from src.motor import PMSMParameters
from src.rotating_identification import (
    FluxEstimate,
    RotatingMeasurements,
    estimate_flux_linkage,
)


@dataclass(frozen=True)
class CommissioningResult:
    electrical: ElectricalEstimate | None
    flux: FluxEstimate | None
    pole_pairs: int
    quality: CommissioningQuality = CommissioningQuality(False, ("quality_not_assessed",))

    def retuned_controller_parameters(self, prior: PMSMParameters) -> PMSMParameters:
        """Replace identified electrical constants, preserving known mechanics.

        The current and speed controller constructors calculate new PI gains
        from the returned parameters. The prior object is not modified.
        """
        if not self.quality.accepted or self.electrical is None or self.flux is None:
            raise CommissioningRejectedError(self.quality)
        if prior.pole_pairs != self.pole_pairs:
            raise ValueError("Controller pole-pair count differs from commissioning data")
        return replace(
            prior,
            Rs=self.electrical.Rs,
            Ld=self.electrical.Ld,
            Lq=self.electrical.Lq,
            psi_f=self.flux.psi_f,
        )


def commission_from_measurements(
    standstill_data: StandstillMeasurements,
    rotating_data: RotatingMeasurements,
    known_pole_pairs: int,
    policy: QualityPolicy = QualityPolicy(),
) -> CommissioningResult:
    """Estimate and assess using measurements; failures return explicit rejection."""
    electrical = flux = None
    stage = "standstill"
    try:
        electrical = estimate_standstill_parameters(standstill_data)
        stage = "rotating"
        flux = estimate_flux_linkage(rotating_data, electrical, known_pole_pairs)
    except (ValueError, FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
        quality = CommissioningQuality(False, (f"{stage}: {exc}",), estimator_failure=str(exc))
    else:
        quality = assess_commissioning(electrical, flux, known_pole_pairs, policy)
    return CommissioningResult(electrical, flux, known_pole_pairs, quality)


class CommissioningRejectedError(ValueError):
    def __init__(self, quality):
        self.quality = quality
        super().__init__("Commissioning rejected: " + "; ".join(quality.rejection_reasons))
