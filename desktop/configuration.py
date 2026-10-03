"""Qt forms; field defaults are read from the existing workflow configuration."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QLabel,
    QScrollArea, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from app.localization import LANGUAGES, t
from desktop.services import configuration_from_inputs
from src.engineering_workflow import EngineeringWorkflowConfig, scenarios


class ConfigurationPanel(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setMinimumWidth(320)
        self.controls, self.labels, self.groups, self.notes = {}, [], [], []
        body = QWidget()
        self.layout = QVBoxLayout(body)
        self.layout.setContentsMargins(10, 8, 10, 8)
        default = EngineeringWorkflowConfig()
        self.language = QComboBox()
        for code, label in LANGUAGES.items(): self.language.addItem(label, code)
        self.layout.addWidget(QLabel("Dil / Language"))
        self.layout.addWidget(self.language)
        form = self.group("Drive / scenario configuration")
        self.number(form, "pole_pairs", "Known pole pairs [pairs]", default.prior_assumptions.pole_pairs, 1, 32, integer=True)
        self.number(form, "bus", "Nominal DC bus [V]", default.dc_bus_voltage_v, .1, 1e6)
        form = self.group("Commissioning setup")
        self.combo(form, "mode", "Commissioning mode", ("one_shot", "adaptive"), default.mode)
        self.number(form, "seed", "Deterministic seed", default.seed, 0, 2**31-3, integer=True)
        self.combo(form, "prior_mode", "Initial model", ("default", "custom"), "default")
        form = self.group("Custom prior / fallback model")
        self.prior_group = form.parentWidget()
        self.motor_fields(form, "prior", default.prior_assumptions)
        self.controls["prior_mode"].currentIndexChanged.connect(self.update_prior_visibility)
        self.update_prior_visibility()
        form = self.group("Parameters to estimate")
        self.note(form, "Rs, Ld, Lq, psi_f, J, B")
        self.note(form, "Estimated from sampled voltage, current and speed measurements.")
        form = self.group("Operating request")
        for key, label, value, lower, upper in (
            ("target", "Speed target [rpm]", default.speed_target_rpm, 1, 1e6),
            ("load", "External operating load [N m]", default.load_torque_nm, 0, 1e6),
            ("limit", "Operating iq reference limit [A]", default.current_limit_a, .01, 1e6),
            ("deadline", "Dynamic deadline [s]", default.deadline_s, .01, 5),
            ("hold", "Required dynamic hold [s]", default.hold_time_s, .001, 1e6)):
            self.number(form, key, label, value, lower, upper, 4 if key == "load" else 3, .001 if key == "hold" else .01)
        form = self.group("Simulation errors")
        self.combo(form, "scenario", "M17 simulation preset", tuple(s.name for s in scenarios()), default.scenario)
        self.combo(form, "exposure", "Impairment exposure", ("combined", "commissioning_only", "operation_only"), default.exposure)
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setObjectName("advanced_simulation_settings")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.layout.addWidget(self.advanced_toggle)
        self.advanced_body = QWidget()
        advanced_layout = QVBoxLayout(self.advanced_body)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.advanced_body)
        form = self.group("Simulation Motor Model", advanced_layout)
        self.note(form, "These values define only the simulated plant. Estimators do not receive them.")
        self.motor_fields(form, "truth", default.simulation_truth)
        form = self.group("Commissioning excitation / noise / validation timing", advanced_layout)
        self.note(form, "Simulation design constraints; no physical hardware-safety guarantee. Mechanical external load is explicitly zero.")
        self.number(form, "noise_i", "Recorded electrical current noise SD [A]", default.standstill.current_noise_std_a, 0, 1e6, 5, .001)
        self.number(form, "noise_v", "Recorded voltage noise SD [V]", default.standstill.voltage_noise_std_v, 0, 1e6, 5, .001)
        self.number(form, "rotor_speed", "Driven-rotor commissioning speed [rpm]", default.rotating.speed_rpm, 100, 1200)
        self.number(form, "excitation", "Standstill voltage-program scale [dimensionless]", 1., 0, 1.5, 2, .01)
        form = self.group("Validation timing", advanced_layout)
        self.number(form, "duration", "Control-validation duration [s]", default.simulation_duration_s, .01, 5, 3)
        self.number(form, "step_time", "Operating load-step time [s]", default.load_step_time_s, 0, 1e6, 3)
        self.advanced_toggle.toggled.connect(self.update_advanced_visibility)
        self.update_advanced_visibility(False)
        self.layout.addStretch()
        self.setWidget(body)
        self.retranslate()

    def group(self, message, container_layout=None):
        box = QGroupBox()
        self.groups.append((box, message))
        form = QFormLayout(box)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        (container_layout if container_layout is not None else self.layout).addWidget(box)
        return form

    def motor_fields(self, form, prefix, motor):
        for name, unit, step in (("Rs", "ohm", .001), ("Ld", "H", 1e-7), ("Lq", "H", 1e-7),
                                 ("psi_f", "Wb", 1e-6), ("J", "kg m²", 1e-7), ("B", "N m s/rad", 1e-7)):
            self.number(form, prefix+"_"+name, f"{name} [{unit}]", getattr(motor, name), 0., 1e6, 7, step)

    def update_prior_visibility(self):
        self.prior_group.setVisible(self.controls["prior_mode"].currentData() == "custom")

    def update_advanced_visibility(self, expanded):
        self.advanced_body.setVisible(expanded)
        self.advanced_toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)

    def note(self, form, message):
        label = QLabel()
        label.setWordWrap(True)
        self.notes.append((label, message))
        form.addRow(label)

    def number(self, form, key, message, value, lower, upper, decimals=2, step=.01, integer=False):
        control = QSpinBox() if integer else QDoubleSpinBox()
        if not integer:
            control.setDecimals(decimals)
            control.setSingleStep(step)
        control.setRange(lower, upper)
        control.setValue(value)
        control.setKeyboardTracking(False)
        self.add(form, key, message, control)

    def combo(self, form, key, message, codes, default):
        control = QComboBox()
        for code in codes: control.addItem(t(code), code)
        control.setCurrentIndex(control.findData(default))
        self.add(form, key, message, control)

    def add(self, form, key, message, control):
        control.setObjectName(key)
        self.controls[key] = control
        label = QLabel()
        label.setWordWrap(True)
        label.setBuddy(control)
        self.labels.append((label, message))
        form.addRow(label, control)

    def values(self):
        return {key: widget.currentData() if isinstance(widget, QComboBox) else widget.value()
                for key, widget in self.controls.items()}

    def configuration(self):
        return configuration_from_inputs(self.values())

    def retranslate(self):
        self.advanced_toggle.setText(t("Advanced Simulation Settings"))
        for widget, message in self.groups: widget.setTitle(t(message))
        for label, message in self.labels+self.notes: label.setText(t(message))
        for control in self.controls.values():
            if isinstance(control, QComboBox):
                for i in range(control.count()): control.setItemText(i, t(control.itemData(i)))
