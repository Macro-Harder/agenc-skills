import json
import argparse
import sys

MEMBERS = {
    "Builder": {
        "job": "implement one unit from the spec plus its tests; update the engineering docs for what it touched",
        "inputs": "spec, unit boundary from Architect, existing code in scope",
        "outputs": "diff, test list, doc updates",
        "done_check": "unit tests pass in the Verifier run; diff inside file scope",
        "brief_line": "You are the Builder. Implement unit <id> from <spec> with its tests inside <file scope>, update the engineering docs you touched, and write the diff summary and test list to <out>/build-<id>.md."
    },
    "Verifier": {
        "job": "independent check: run the full suite and drive the real thing (CLI or API) like a user; never edits code",
        "inputs": "the integrated code, test suite, real usage scenarios",
        "outputs": "literal output artifact",
        "done_check": "suite and real-use outputs saved verbatim; verdict PASS/FAIL per done-check",
        "brief_line": "You are the Verifier. Do not trust the Builder. Run <suite cmd>, drive <CLI/API> like a user, save literal output to <out>/verify-<id>.txt and edit no source files."
    },
    "Architect": {
        "job": "name data shapes, types and module boundaries before any build",
        "inputs": "project scope, modules_touched, cross_boundary_count, new_core_types, new_modules",
        "outputs": "design note with types and boundaries",
        "done_check": "every unit maps to a named boundary; no build starts before it",
        "brief_line": "You are the Architect. Name data shapes, types and module boundaries from <project scope>, <modules_touched>, <cross_boundary_count>, <new_core_types> and <new_modules> before any build, and write the design note to <out>/design-<id>.md."
    },
    "Test Author": {
        "job": "write behaviour tests from the spec independently of the Builder",
        "inputs": "spec, money_or_state, builder_tests_only_proof",
        "outputs": "test files that fail before the build",
        "done_check": "tests fail on the base sha and cite spec lines",
        "brief_line": "You are the Test Author. Write behaviour tests from <spec> independently of the Builder using <money_or_state> and <builder_tests_only_proof>, and write the test files to <out>/test-<id>.md."
    },
    "Integrator": {
        "job": "merge parallel worktrees in order, resolve conflicts, hand off to the Verifier",
        "inputs": "parallel_units, parallel branches from Builders",
        "outputs": "one integrated branch and merge log",
        "done_check": "all unit branches merged; no conflict markers; handed to Verifier",
        "brief_line": "You are the Integrator. Merge parallel worktrees in order from <parallel_units> and <parallel_branches_from_builders>, resolve conflicts, hand off to the Verifier, and write one integrated branch and merge log to <out>/integrate-<id>.md."
    },
    "Codemod Smith": {
        "job": "write a script or codemod for bulk mechanical changes instead of hand edits",
        "inputs": "mechanical_edit_count, files or call sites",
        "outputs": "codemod script plus its diff",
        "done_check": "rerunning the codemod on the result is a no-op",
        "brief_line": "You are the Codemod Smith. Write a script or codemod for <mechanical_edit_count> and <files_or_call_sites> instead of hand edits, and write the codemod script plus its diff to <out>/codemod-<id>.md."
    },
    "Simplifier": {
        "job": "delete dead code, shims, one-caller wrappers and comment slop",
        "inputs": "diff_lines, refactor_or_migration",
        "outputs": "a diff that reduces line count",
        "done_check": "net lines removed; suite unchanged",
        "brief_line": "You are the Simplifier. Delete dead code, shims, one-caller wrappers and comment slop from <diff_lines> and <refactor_or_migration>, and write a diff that reduces line count to <out>/simplify-<id>.md."
    },
    "Blast-Radius Reviewer": {
        "job": "find callers and dependents a change could break; read-only",
        "inputs": "interface_changes",
        "outputs": "list of affected callers with file:line",
        "done_check": "every changed interface has its callers listed and checked",
        "brief_line": "You are the Blast-Radius Reviewer. Find callers and dependents a change could break from <interface_changes>, list of affected callers with file:line to <out>/blast-<id>.md and edit no source files."
    },
    "Bench Runner": {
        "job": "measure any perf claim and name the limiter",
        "inputs": "perf_claims",
        "outputs": "benchmark command, raw numbers, limiter",
        "done_check": "each number has a command, raw output and named limiter",
        "brief_line": "You are the Bench Runner. Measure any <perf_claims> and name the limiter, write benchmark command, raw numbers, limiter to <out>/bench-<id>.md and edit no source files."
    },
    "Docs Writer": {
        "job": "standalone docs for a large project or new subsystem",
        "inputs": "project_size, new_subsystem",
        "outputs": "docs files",
        "done_check": "docs match the code at the sha",
        "brief_line": "You are the Docs Writer. Write standalone docs for <project_size> and <new_subsystem>, and write docs files to <out>/docs-<id>.md."
    },
    "Fixer": {
        "job": "fix confirmed findings only: failing test first, smallest fix, full suite rerun",
        "inputs": "confirmed_findings",
        "outputs": "fixed code, new test",
        "done_check": "new test fails before, passes after; full suite green in a Verifier run",
        "brief_line": "You are the Fixer. For confirmed finding <finding id>, write failing test first, make smallest fix, rerun full suite, and write fixed code and new test to <out>/fix-<id>.md."
    },
    "Rebuilder": {
        "job": "rebuild from the spec and data shape after a three-strike write-up; never reuse the failed premise",
        "inputs": "three_strike",
        "outputs": "new implementation from spec",
        "done_check": "write-up's shared premise named and not relied on; Verifier passes",
        "brief_line": "You are the Rebuilder. From the write-up <writeup path>, spec and data shape, rebuild without the failed premise, and write new implementation to <out>/rebuild-<id>.md."
    }
}

def pick_roster(project, diff_threshold=400, mechanical_threshold=5):
    if not isinstance(project, dict):
        return {"error": "input must be a JSON object"}
    allowed = {
        "modules_touched", "new_modules", "cross_boundary_count", "money_or_state",
        "new_core_types", "builder_tests_only_proof", "parallel_units",
        "mechanical_edit_count", "diff_lines", "refactor_or_migration",
        "interface_changes", "perf_claims", "project_size", "new_subsystem",
        "confirmed_findings", "three_strike"
    }
    for k in project:
        if k not in allowed:
            return {"error": f"unknown key: {k}"}
    defaults = {
        "modules_touched": 1,
        "new_modules": 0,
        "cross_boundary_count": 0,
        "money_or_state": False,
        "new_core_types": False,
        "builder_tests_only_proof": False,
        "parallel_units": 1,
        "mechanical_edit_count": 0,
        "diff_lines": 0,
        "refactor_or_migration": False,
        "interface_changes": False,
        "perf_claims": False,
        "project_size": "small",
        "new_subsystem": False,
        "confirmed_findings": 0,
        "three_strike": False,
    }
    inputs = {}
    for k, default in defaults.items():
        if k in project:
            val = project[k]
            if k == "project_size":
                if not isinstance(val, str) or val not in ["small", "medium", "large"]:
                    return {"error": "project_size must be small|medium|large"}
            elif k in ["modules_touched", "new_modules", "cross_boundary_count", "parallel_units", "mechanical_edit_count", "diff_lines", "confirmed_findings"]:
                if isinstance(val, bool) or not isinstance(val, int):
                    return {"error": f"{k} must be int"}
                if val < 0:
                    return {"error": f"{k} must be non-negative"}
            elif not isinstance(val, bool):
                return {"error": f"{k} must be bool"}
            inputs[k] = val
        else:
            inputs[k] = default
    stage_defs = [
        ["Architect"],
        ["Test Author", "Builder"],
        ["Codemod Smith"],
        ["Integrator"],
        ["Simplifier"],
        ["Blast-Radius Reviewer"],
        ["Verifier"],
        ["Bench Runner"],
        ["Docs Writer"]
    ]
    member_info = {}
    builder_reason = "core: code, tests and docs for one unit"
    if inputs["parallel_units"] > 1:
        builder_reason += f" x{inputs['parallel_units']} parallel"
    member_info["Builder"] = {"kind": "core", "reason": builder_reason}
    member_info["Verifier"] = {"kind": "core", "reason": "core: independent run of the full suite and the real thing; literal artifacts; no edits"}
    arch_reason = None
    if inputs["new_modules"] > 0 or inputs["cross_boundary_count"] > 1 or inputs["new_core_types"]:
        triggers = []
        if inputs["new_modules"] > 0:
            triggers.append(f"new_modules={inputs['new_modules']} > 0")
        if inputs["cross_boundary_count"] > 1:
            triggers.append(f"cross_boundary_count={inputs['cross_boundary_count']} > 1")
        if inputs["new_core_types"]:
            triggers.append("new_core_types=true")
        arch_reason = "; ".join(triggers)
    else:
        skipped_arch = f"no new modules, cross_boundary_count={inputs['cross_boundary_count']}, no new core types"
    if arch_reason:
        member_info["Architect"] = {"kind": "optional", "reason": arch_reason}
    test_author_reason = None
    if inputs["money_or_state"] or inputs["builder_tests_only_proof"]:
        triggers = []
        if inputs["money_or_state"]:
            triggers.append("money_or_state=true")
        if inputs["builder_tests_only_proof"]:
            triggers.append("builder_tests_only_proof=true")
        test_author_reason = "; ".join(triggers)
    else:
        skipped_test = "no money_or_state, no builder_tests_only_proof"
    if test_author_reason:
        member_info["Test Author"] = {"kind": "optional", "reason": test_author_reason}
    integrator_reason = None
    if inputs["parallel_units"] >= 2:
        integrator_reason = f"parallel_units={inputs['parallel_units']} >= 2"
    else:
        skipped_int = f"parallel_units={inputs['parallel_units']} < 2"
    if integrator_reason:
        member_info["Integrator"] = {"kind": "optional", "reason": integrator_reason}
    codemod_reason = None
    if inputs["mechanical_edit_count"] >= mechanical_threshold:
        codemod_reason = f"mechanical_edit_count={inputs['mechanical_edit_count']} >= {mechanical_threshold}"
    else:
        skipped_code = f"mechanical_edit_count={inputs['mechanical_edit_count']} < {mechanical_threshold}"
    if codemod_reason:
        member_info["Codemod Smith"] = {"kind": "optional", "reason": codemod_reason}
    simplifier_reason = None
    if inputs["diff_lines"] > diff_threshold or inputs["refactor_or_migration"]:
        triggers = []
        if inputs["diff_lines"] > diff_threshold:
            triggers.append(f"diff_lines={inputs['diff_lines']} > {diff_threshold}")
        if inputs["refactor_or_migration"]:
            triggers.append("refactor_or_migration=true")
        simplifier_reason = "; ".join(triggers)
    else:
        skipped_simp = f"diff_lines={inputs['diff_lines']} <= {diff_threshold}, no refactor_or_migration"
    if simplifier_reason:
        member_info["Simplifier"] = {"kind": "optional", "reason": simplifier_reason}
    blast_reason = None
    if inputs["interface_changes"]:
        blast_reason = "interface_changes=true"
    else:
        skipped_blast = "no interface_changes"
    if blast_reason:
        member_info["Blast-Radius Reviewer"] = {"kind": "optional", "reason": blast_reason}
    bench_reason = None
    if inputs["perf_claims"]:
        bench_reason = "perf_claims=true"
    else:
        skipped_bench = "no perf_claims"
    if bench_reason:
        member_info["Bench Runner"] = {"kind": "optional", "reason": bench_reason}
    docs_reason = None
    if inputs["project_size"] == "large" or inputs["new_subsystem"]:
        triggers = []
        if inputs["project_size"] == "large":
            triggers.append("project_size=large")
        if inputs["new_subsystem"]:
            triggers.append("new_subsystem=true")
        docs_reason = "; ".join(triggers)
    else:
        skipped_docs = "Builder writes docs"
    if docs_reason:
        member_info["Docs Writer"] = {"kind": "optional", "reason": docs_reason}
    event_driven = []
    if inputs["three_strike"]:
        fixer_trigger = "three_strike=true: Rebuilder replaces Fixer for this failure"
        fixer_status = "on hold"
    else:
        if inputs["confirmed_findings"] > 0:
            fixer_trigger = f"confirmed_findings={inputs['confirmed_findings']} > 0"
            fixer_status = "launch now"
        else:
            fixer_trigger = "confirmed_findings > 0"
            fixer_status = "on trigger"
    event_driven.append({"member": "Fixer", "status": fixer_status, "trigger": fixer_trigger})
    if not inputs["three_strike"] and inputs["confirmed_findings"] > 0:
        member_info["Fixer"] = {"kind": "event", "reason": fixer_trigger}
    rebuilder_trigger = "three_strike=true" if inputs["three_strike"] else "three_strike"
    rebuilder_status = "launch now" if inputs["three_strike"] else "on trigger"
    event_driven.append({"member": "Rebuilder", "status": rebuilder_status, "trigger": rebuilder_trigger})
    if inputs["three_strike"]:
        member_info["Rebuilder"] = {"kind": "event", "reason": "three_strike=true"}
    roster = []
    for stage in stage_defs:
        for m in stage:
            if m in member_info:
                info = member_info[m]
                roster.append({"member": m, "kind": info["kind"], "reason": info["reason"]})
    if not inputs["three_strike"] and inputs["confirmed_findings"] > 0:
        roster.append({"member": "Fixer", "kind": "event", "reason": fixer_trigger})
    if inputs["three_strike"]:
        roster.append({"member": "Rebuilder", "kind": "event", "reason": "three_strike=true"})
    launch_order = []
    for stage in stage_defs:
        active = [m for m in stage if m in member_info]
        if active:
            launch_order.append(active)
    skipped = []
    if "Architect" not in member_info:
        skipped.append({"member": "Architect", "reason": f"no new modules, cross_boundary_count={inputs['cross_boundary_count']}, no new core types"})
    if "Test Author" not in member_info:
        skipped.append({"member": "Test Author", "reason": "no money_or_state, no builder_tests_only_proof"})
    if "Integrator" not in member_info:
        skipped.append({"member": "Integrator", "reason": f"parallel_units={inputs['parallel_units']} < 2"})
    if "Codemod Smith" not in member_info:
        skipped.append({"member": "Codemod Smith", "reason": f"mechanical_edit_count={inputs['mechanical_edit_count']} < {mechanical_threshold}"})
    if "Simplifier" not in member_info:
        skipped.append({"member": "Simplifier", "reason": f"diff_lines={inputs['diff_lines']} <= {diff_threshold}, no refactor_or_migration"})
    if "Blast-Radius Reviewer" not in member_info:
        skipped.append({"member": "Blast-Radius Reviewer", "reason": "no interface_changes"})
    if "Bench Runner" not in member_info:
        skipped.append({"member": "Bench Runner", "reason": "no perf_claims"})
    if "Docs Writer" not in member_info:
        skipped.append({"member": "Docs Writer", "reason": "Builder writes docs"})
    if inputs["three_strike"]:
        skipped.append({"member": "Fixer", "reason": "three_strike=true: Rebuilder replaces Fixer for this failure"})
    elif inputs["confirmed_findings"] == 0:
        skipped.append({"member": "Fixer", "reason": "confirmed_findings=0"})
    if not inputs["three_strike"]:
        skipped.append({"member": "Rebuilder", "reason": "no three-strike write-up"})
    result = {
        "roster": roster,
        "skipped": skipped,
        "launch_order": launch_order,
        "event_driven": event_driven,
        "inputs": inputs,
        "size": len(roster),
        "principle": "smallest roster that covers the risks; every member justified"
    }
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", default="-")
    parser.add_argument("--diff-threshold", type=int, default=400)
    parser.add_argument("--mechanical-threshold", type=int, default=5)
    parser.add_argument("--describe", action="store_true")
    args = parser.parse_args()
    if args.describe:
        print(json.dumps(MEMBERS, indent=2))
        sys.exit(0)
    try:
        if args.input == "-":
            raw = sys.stdin.read().strip()
            project = json.loads(raw) if raw else {}
        else:
            with open(args.input, encoding="utf-8") as f:
                project = json.load(f)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"invalid JSON: {str(e)}"}))
        sys.exit(2)
    except Exception as e:
        print(json.dumps({"error": f"failed to read input: {str(e)}"}))
        sys.exit(2)
    result = pick_roster(project, args.diff_threshold, args.mechanical_threshold)
    if isinstance(result, dict) and "error" in result:
        print(json.dumps(result))
        sys.exit(2)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
