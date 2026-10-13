"""Per-function workflow: generate -> static checks -> pytest -> classify -> verify -> (retry/regenerate)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..generator.generator import GenerationResult, TestGenerator
from ..generator.llm import LLMClient
from ..generator.prompts import generated_test_filename
from .classify import (
    ACCEPTED,
    NEEDS_REVIEW,
    POSSIBLE_BUG,
    REJECTED,
    Observation,
    function_status,
    observe,
    trim,
)
from .runner import PytestRun, run_pytest
from .static_checks import static_check, test_function_names, test_function_sources
from .verify import verify_failure

Log = Callable[[str, str], None]


@dataclass
class FunctionContext:
    repo: Path
    job_dir: Path
    tests_dir: Path
    python: str
    timeout: float
    client: LLMClient
    max_retries: int = 2
    log: Log = lambda level, msg: None  # noqa: E731


@dataclass
class FunctionOutcome:
    status: str
    tests: list[dict] = field(default_factory=list)
    code: str = ""
    test_file: str | None = None
    attempts: int = 0
    error: str | None = None


def _record(name: str, status: str, code: str, attempts: int, reason: str = "", obs: Observation | None = None,
            verdict: dict | None = None) -> dict:
    return {
        "name": name,
        "status": status,
        "code": code,
        "attempts": attempts,
        "reason": reason,
        "expected": obs.expected if obs else None,
        "actual": obs.actual if obs else None,
        "traceback": obs.traceback if obs and status in (POSSIBLE_BUG, NEEDS_REVIEW, REJECTED) else "",
        "verdict": verdict,
    }


def _all_rejected(code: str, attempts: int, reason: str) -> list[dict]:
    sources = test_function_sources(code)
    if not sources:
        return [_record("(generated file)", REJECTED, code, attempts, reason)]
    return [_record(n, REJECTED, src, attempts, reason) for n, src in sources.items()]


def process_function(fn: dict, call_sites: list[str], ctx: FunctionContext) -> FunctionOutcome:
    gen = TestGenerator(ctx.client, max_retries=ctx.max_retries)
    check = lambda code: static_check(code, fn).problem  # noqa: E731
    test_path = Path(ctx.tests_dir) / generated_test_filename(fn)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    label = fn["qualname"]

    result: GenerationResult = gen.generate(fn, call_sites, check)
    for h in result.history:
        ctx.log("warn", f"Static check failed for `{label}` ({h['problem']}); retrying")
    regenerated_for_test_wrong = False

    while True:
        test_path.write_text(result.code)
        if not result.ok:
            return FunctionOutcome(REJECTED, _all_rejected(result.code, result.attempts, result.problem or ""),
                                   result.code, str(test_path), result.attempts)

        run1 = run_pytest(test_path, ctx.repo, ctx.job_dir, ctx.python, ctx.timeout)
        sources = test_function_sources(result.code)
        if run1.timed_out:
            reason = f"Timed out after {int(ctx.timeout)}s"
            tests = [_record(n, NEEDS_REVIEW, src, result.attempts, reason) for n, src in sources.items()]
            return FunctionOutcome(NEEDS_REVIEW, tests, result.code, str(test_path), result.attempts)

        observations = {n: observe(c, test_path.name, fn["name"]) for n, c in run1.cases.items()}
        invalid_problem = None
        if run1.collection_error:
            invalid_problem = f"Collection error: {trim(run1.collection_error, 12)}"
        else:
            bad = [(n, o) for n, o in observations.items() if o.kind == "invalid"]
            if bad:
                invalid_problem = "; ".join(f"{n}: {o.reason}" for n, o in bad[:3])
                invalid_problem += "\n" + trim(bad[0][1].traceback, 10)
            elif not observations:
                invalid_problem = "pytest collected no tests from the file"
        if invalid_problem and result.attempts <= ctx.max_retries:
            ctx.log("warn", f"Invalid test for `{label}` ({invalid_problem.splitlines()[0][:160]}); retrying")
            result.history.append({"code": result.code, "problem": invalid_problem})
            result.code = gen.retry(result.prompt, result.code, invalid_problem)
            result.attempts += 1
            gen.fix_until_valid(result, check)
            continue
        if run1.collection_error or not observations:
            return FunctionOutcome(REJECTED, _all_rejected(result.code, result.attempts, invalid_problem or ""),
                                   result.code, str(test_path), result.attempts)

        failures = [n for n, o in observations.items() if o.kind == "failure"]
        run2: PytestRun | None = None
        if failures:  # rerun once to rule out flakiness
            run2 = run_pytest(test_path, ctx.repo, ctx.job_dir, ctx.python, ctx.timeout)

        tests: list[dict] = []
        test_wrong: list[tuple[str, dict]] = []
        for name in test_function_names(result.code) or list(observations):
            obs = observations.get(name)
            src = sources.get(name, "")
            if obs is None:
                tests.append(_record(name, NEEDS_REVIEW, src, result.attempts, "No result reported by pytest"))
                continue
            if run2 is not None:
                if run2.timed_out:
                    tests.append(_record(name, NEEDS_REVIEW, src, result.attempts,
                                         f"Timed out after {int(ctx.timeout)}s on rerun", obs))
                    continue
                c2 = run2.cases.get(name)
                if c2 is None or c2.outcome != run1.cases[name].outcome:
                    tests.append(_record(name, NEEDS_REVIEW, src, result.attempts,
                                         "Flaky: result differs between two runs", obs))
                    continue
            if obs.kind == "passed":
                tests.append(_record(name, ACCEPTED, src, result.attempts, "All assertions passed"))
            elif obs.kind == "skipped":
                tests.append(_record(name, NEEDS_REVIEW, src, result.attempts, obs.reason, obs))
            elif obs.kind == "invalid":
                tests.append(_record(name, REJECTED, src, result.attempts, obs.reason, obs))
            else:
                ctx.log("info", f"Verifying failing test `{name}` for `{label}`...")
                verdict = verify_failure(ctx.client, fn, src, f"{obs.reason}\n{obs.traceback}")
                if verdict["verdict"] == "likely_bug":
                    tests.append(_record(name, POSSIBLE_BUG, src, result.attempts, obs.reason, obs, verdict))
                elif verdict["verdict"] == "test_wrong":
                    if regenerated_for_test_wrong:
                        reason = f"Test judged wrong after regeneration: {verdict['reason']}"
                        tests.append(_record(name, REJECTED, src, result.attempts, reason, obs, verdict))
                    else:
                        test_wrong.append((name, verdict))
                        tests.append(_record(name, REJECTED, src, result.attempts,
                                             f"Test judged wrong: {verdict['reason']}", obs, verdict))
                else:
                    tests.append(_record(name, NEEDS_REVIEW, src, result.attempts,
                                         f"Unclear: {verdict['reason']}", obs, verdict))

        if test_wrong and not regenerated_for_test_wrong:
            regenerated_for_test_wrong = True
            name, verdict = test_wrong[0]
            obs = observations[name]
            problem = (f"The test `{name}` failed ({obs.reason}) and review concluded the TEST is wrong: "
                       f"{verdict['reason']} Fix the expected values.\n{trim(obs.traceback, 8)}")
            ctx.log("warn", f"Test for `{label}` judged wrong ({verdict['reason'][:120]}); regenerating")
            result.history.append({"code": result.code, "problem": problem})
            result.code = gen.retry(result.prompt, result.code, problem)
            result.attempts += 1
            gen.fix_until_valid(result, check)
            continue

        status = function_status([t["status"] for t in tests])
        return FunctionOutcome(status, tests, result.code, str(test_path), result.attempts)
