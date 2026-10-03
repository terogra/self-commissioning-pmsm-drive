"""Application boundary: configuration and existing backend operations only."""

from dataclasses import replace
from pathlib import Path

from src.engineering_bundle import run_bundle_zip
from src.engineering_workflow import (
    EngineeringWorkflowConfig, MotorConfiguration, export_firmware_configuration,
    run_engineering_workflow,
)


def configuration_from_inputs(values):
    default = EngineeringWorkflowConfig()
    pairs = values["pole_pairs"]
    motors = {}
    for prefix in ("truth", "prior"):
        if prefix == "prior" and values["prior_mode"] == "default":
            motors[prefix] = replace(default.prior_assumptions, pole_pairs=pairs)
        else:
            motors[prefix] = MotorConfiguration(**{name: values[prefix+"_"+name]
                for name in ("Rs", "Ld", "Lq", "psi_f", "J", "B")}, pole_pairs=pairs)
    return replace(default, simulation_truth=motors["truth"], prior_assumptions=motors["prior"],
        scenario=values["scenario"], mode=values["mode"], exposure=values["exposure"], seed=values["seed"],
        dc_bus_voltage_v=values["bus"], speed_target_rpm=values["target"], load_torque_nm=values["load"],
        current_limit_a=values["limit"], deadline_s=values["deadline"], hold_time_s=values["hold"],
        simulation_duration_s=values["duration"], load_step_time_s=values["step_time"],
        standstill=replace(default.standstill, current_noise_std_a=values["noise_i"],
            voltage_noise_std_v=values["noise_v"], d_voltage_v=default.standstill.d_voltage_v*values["excitation"],
            q_voltage_v=default.standstill.q_voltage_v*values["excitation"]),
        rotating=replace(default.rotating, current_noise_std_a=values["noise_i"],
            voltage_noise_std_v=values["noise_v"], speed_rpm=values["rotor_speed"]))


class WorkflowService:
    """One source of engineering decisions; injectable for UI boundary tests."""

    def run(self, configuration):
        return run_engineering_workflow(configuration)

    def export_firmware(self, result, path):
        return export_firmware_configuration(result, path)

    def export_bundle(self, result, path):
        Path(path).write_bytes(run_bundle_zip(result))
        return Path(path)
