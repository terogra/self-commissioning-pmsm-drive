"""Combine electrical identification stages and update controller assumptions."""

from dataclasses import dataclass, replace

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
    electrical: ElectricalEstimate
    flux: FluxEstimate
    pole_pairs: int

    def retuned_controller_parameters(self, prior: PMSMParameters) -> PMSMParameters:
        """Replace identified electrical constants, preserving known mechanics.

        The current and speed controller constructors calculate new PI gains
        from the returned parameters. The prior object is not modified.
        """
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
) -> CommissioningResult:
    """Estimate Rs/Ld/Lq, then psi_f, using only sampled measurements."""
    electrical = estimate_standstill_parameters(standstill_data)
    flux = estimate_flux_linkage(rotating_data, electrical, known_pole_pairs)
    return CommissioningResult(electrical=electrical, flux=flux, pole_pairs=known_pole_pairs)
