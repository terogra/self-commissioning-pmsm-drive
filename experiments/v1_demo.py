"""Run nominal acceptance and timing-error rejection demonstrations."""

import argparse
from pathlib import Path

from src.engineering_workflow import EngineeringWorkflowConfig, ROOT, run_engineering_workflow
from src.engineering_bundle import export_run_bundle


DEMO_CONFIGURATIONS = (
    ("nominal", EngineeringWorkflowConfig()),
    ("rejected_timing", EngineeringWorkflowConfig(scenario="timing_one_sample", mode="adaptive")),
)


def generate_demo(output=ROOT/"results/v1_demo"):
    results = []
    for name, config in DEMO_CONFIGURATIONS:
        result = run_engineering_workflow(config)
        paths = export_run_bundle(result, Path(output)/name)
        print(f"{name}: {result.status}; {len(result.attempts)} attempts; {len(paths)} artifacts", flush=True)
        results.append(result)
    return tuple(results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"results/v1_demo")
    args = parser.parse_args()
    generate_demo(args.output)


if __name__ == "__main__": main()
