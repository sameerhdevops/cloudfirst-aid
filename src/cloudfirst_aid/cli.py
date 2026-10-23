"""Command-line interface for CloudFirst Aid.

Entry point providing incident listing, deep inspection, catalog validation,
deterministic evidence triage, and incident report generation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cloudfirst_aid import __version__
from cloudfirst_aid.catalog import (
    filter_by_category,
    get_scenario_by_id,
    list_categories,
    load_catalog,
    validate_catalog,
)
from cloudfirst_aid.evidence import (
    format_evidence_record,
    load_evidence_fixtures,
    redact_sensitive_fields,
)
from cloudfirst_aid.reports import generate_incident_report, write_incident_report
from cloudfirst_aid.triage import triage_scenario


def _format_table_row(cols: list[str], widths: list[int]) -> str:
    parts = [col.ljust(w) for col, w in zip(cols, widths)]
    return "  ".join(parts)


def cmd_list(args: argparse.Namespace) -> int:
    """List available troubleshooting scenarios."""
    try:
        scenarios = load_catalog()
    except Exception as exc:
        print(f"Error loading catalog: {exc}", file=sys.stderr)
        return 1

    if args.category:
        scenarios = filter_by_category(scenarios, args.category)

    if not scenarios:
        if args.category:
            print(f"No scenarios found in category '{args.category}'.")
            cats = list_categories(load_catalog())
            print(f"Available categories: {', '.join(cats)}")
        else:
            print("No scenarios found in catalog.")
        return 0

    print(f"\nCloudFirst Aid - Scenario Catalog ({len(scenarios)} scenarios)\n")
    headers = ["ID", "CATEGORY", "SEVERITY", "DIFFICULTY", "DEMO", "TITLE"]
    widths = [9, 13, 10, 14, 6, 42]

    print(_format_table_row(headers, widths))
    print(_format_table_row(["-" * w for w in widths], widths))

    for s in scenarios:
        demo_flag = "[DEMO]" if s.has_demo else "  -  "
        title_truncated = s.title if len(s.title) <= 42 else s.title[:39] + "..."
        row = [s.id, s.category, s.severity.upper(), s.difficulty.capitalize(), demo_flag, title_truncated]
        print(_format_table_row(row, widths))

    print("\nUse 'cloudfirst-aid show <ID>' for scenario details and investigation steps.")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Display scenario details, initial symptoms, and investigation steps."""
    try:
        scenarios = load_catalog()
    except Exception as exc:
        print(f"Error loading catalog: {exc}", file=sys.stderr)
        return 1

    scenario = get_scenario_by_id(scenarios, args.scenario_id)
    if not scenario:
        print(f"Error: Scenario '{args.scenario_id}' not found in catalog.", file=sys.stderr)
        return 1

    print(f"\n{'=' * 78}")
    print(f"[{scenario.id}] {scenario.title}")
    print(f"{'=' * 78}")
    print(f"Category:   {scenario.category.capitalize()} | Severity: {scenario.severity.upper()} | Difficulty: {scenario.difficulty.capitalize()}")
    if scenario.environment:
        print(f"Prerequisites: {scenario.environment}")

    print(f"\n[REPORTED SYMPTOM]\n  {scenario.symptom}")

    if scenario.initial_observations:
        print("\n[INITIAL OBSERVATIONS]")
        for obs in scenario.initial_observations:
            print(f"  * {obs}")

    if scenario.possible_causes:
        print("\n[POSSIBLE ROOT CAUSES]")
        for c in scenario.possible_causes:
            print(f"  * {c.cause} ({c.likelihood.upper()})")
            if c.evidence_needed:
                print(f"    Required confirmation: {c.evidence_needed}")

    if scenario.investigation_steps:
        print("\n[RECOMMENDED INVESTIGATION SEQUENCE]")
        for step in scenario.investigation_steps:
            print(f"\n  Step {step.order}: {step.title}")
            if step.command:
                print(f"    Command: {step.command}")
            if step.explanation:
                print(f"    Purpose: {step.explanation}")
            if step.what_to_look_for:
                print(f"    Observe: {step.what_to_look_for}")

    if scenario.verification:
        print(f"\n[VERIFICATION]\n  {scenario.verification}")

    if scenario.references:
        print("\n[PRIMARY REFERENCES]")
        for ref in scenario.references:
            print(f"  * {ref}")

    print(f"\nTip: Run 'cloudfirst-aid triage {scenario.id}' to test with evidence fixtures.")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate scenario catalog structural integrity and consistency."""
    try:
        scenarios = load_catalog()
    except Exception as exc:
        print(f"FAIL: Cannot read catalog: {exc}", file=sys.stderr)
        return 1

    print(f"Validating {len(scenarios)} scenario files...")
    errors = validate_catalog(scenarios)

    if errors:
        print(f"\nFAILED with {len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("OK: Catalog is structurally valid.")
    print(f"  Total Scenarios: {len(scenarios)}")
    print(f"  Categories:      {', '.join(list_categories(scenarios))}")
    print(f"  With Demo:       {sum(1 for s in scenarios if s.has_demo)}")
    print(f"  With Runbook:    {sum(1 for s in scenarios if s.has_runbook)}")
    return 0


def cmd_triage(args: argparse.Namespace) -> int:
    """Evaluate diagnostic evidence against troubleshooting rules for a scenario."""
    try:
        scenarios = load_catalog()
    except Exception as exc:
        print(f"Error loading catalog: {exc}", file=sys.stderr)
        return 1

    scenario = get_scenario_by_id(scenarios, args.scenario_id)
    if not scenario:
        print(f"Error: Scenario '{args.scenario_id}' not found.", file=sys.stderr)
        return 1

    evidence = load_evidence_fixtures(scenario.id)
    print(f"\nEvaluating Diagnostic Rules for [{scenario.id}] {scenario.title}")
    print(f"Loaded {len(evidence)} evidence fixture item(s).")

    findings = triage_scenario(scenario.id, evidence)

    print("\n--- Diagnostic Findings ---")
    for idx, f in enumerate(findings, 1):
        status_label = f"[{f.status.upper()}]"
        print(f"\nFinding {idx}: {status_label} {redact_sensitive_fields(f.description)}")
        if f.evidence_ids:
            sanitized_eids = [redact_sensitive_fields(eid) for eid in f.evidence_ids]
            print(f"  Supported by: {', '.join(sanitized_eids)}")
        if f.explanation:
            print(f"  Reasoning:    {redact_sensitive_fields(f.explanation)}")

    print("\nRun 'cloudfirst-aid report " + scenario.id + "' to generate a complete markdown incident report.")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Generate a structured Markdown incident report."""
    try:
        scenarios = load_catalog()
    except Exception as exc:
        print(f"Error loading catalog: {exc}", file=sys.stderr)
        return 1

    scenario = get_scenario_by_id(scenarios, args.scenario_id)
    if not scenario:
        print(f"Error: Scenario '{args.scenario_id}' not found.", file=sys.stderr)
        return 1

    evidence = load_evidence_fixtures(scenario.id)
    findings = triage_scenario(scenario.id, evidence)

    report_md = generate_incident_report(scenario, evidence, findings)

    if args.output:
        out_path = Path(args.output)
        write_incident_report(report_md, out_path)
        print(f"Incident report generated at: {out_path.resolve()}")
    else:
        print(report_md)

    return 0


def cmd_inspect_ec2(args: argparse.Namespace) -> int:
    """Optional read-only live inspection of an EC2 instance."""
    from cloudfirst_aid.aws_readonly import inspect_ec2_instance_readonly

    target_instance = redact_sensitive_fields(args.instance_id)
    print(f"Initiating read-only AWS inspection for instance '{target_instance}'...")
    try:
        items = inspect_ec2_instance_readonly(args.instance_id, region_name=args.region)
        print(f"Successfully collected {len(items)} read-only evidence item(s):")
        for item in items:
            print("\n" + format_evidence_record(item))
        return 0
    except Exception as exc:
        sanitized_err = redact_sensitive_fields(str(exc))
        print(f"AWS Inspection failed: {sanitized_err}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cloudfirst-aid",
        description="CloudFirst Aid - AWS Cloud Support & Linux Troubleshooting Lab CLI",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # list
    p_list = subparsers.add_parser("list", help="List troubleshooting scenarios")
    p_list.add_argument("-c", "--category", help="Filter by category (ec2, linux, networking, iam-s3, monitoring)")

    # show
    p_show = subparsers.add_parser("show", help="Show details and investigation sequence for a scenario")
    p_show.add_argument("scenario_id", help="Scenario ID (e.g. CFA-001)")

    # validate
    subparsers.add_parser("validate", help="Validate catalog integrity and required fields")

    # triage
    p_triage = subparsers.add_parser("triage", help="Run deterministic diagnostic rules on scenario evidence")
    p_triage.add_argument("scenario_id", help="Scenario ID (e.g. CFA-001)")

    # report
    p_report = subparsers.add_parser("report", help="Generate an incident report for a scenario")
    p_report.add_argument("scenario_id", help="Scenario ID (e.g. CFA-001)")
    p_report.add_argument("-o", "--output", help="Write report to markdown file path instead of stdout")

    # inspect-ec2 (optional read-only AWS)
    p_aws = subparsers.add_parser("inspect-ec2", help="Optional: Read-only AWS inspection of an EC2 instance")
    p_aws.add_argument("instance_id", help="Target EC2 Instance ID (e.g. i-0123456789abcdef0)")
    p_aws.add_argument("--region", help="Target AWS Region (e.g. us-east-1)")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    dispatch = {
        "list": cmd_list,
        "show": cmd_show,
        "validate": cmd_validate,
        "triage": cmd_triage,
        "report": cmd_report,
        "inspect-ec2": cmd_inspect_ec2,
    }

    handler = dispatch.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
