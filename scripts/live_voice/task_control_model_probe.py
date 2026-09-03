"""Read-only configured-model probes from supplied cases; no Task/Tool executor."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path


async def run(config: Path, cases_path: Path, output: Path) -> int:
    from dotenv import load_dotenv

    load_dotenv(config / ".env", override=False)
    os.environ["JIUWENSWARM_DATA_DIR"] = str(output.parent / "probe-runtime")
    logging.disable(logging.CRITICAL)
    from jiuwenswarm.common.config import _read_with_retry, _normalize_config, get_default_models, resolve_env_vars
    from jiuwenswarm.common.schema.live_voice_contract_v2 import TurnCommit, TerminalOutcome
    from jiuwenswarm.server.live_voice.p3_model_resolution import ServerModelCatalogResolver
    from jiuwenswarm.server.live_voice.production_task_intent import AuthenticatedTaskFact, AttemptState, TaskAuthorityRead, TaskState
    from jiuwenswarm.server.live_voice.task_semantics import TaskSemanticContext, TaskSemanticResolver
    from jiuwenswarm.server.runtime.agent_adapter.interface_deep import build_model_from_entry

    def configured_models():
        parsed = resolve_env_vars(_read_with_retry(config / "config.yaml"))
        _normalize_config(parsed)
        return get_default_models(parsed)

    observed = []
    class ObservedModel:
        def __init__(self, model):
            self.model = model

        async def invoke(self, **kwargs):
            response = await self.model.invoke(**kwargs)
            observed.append({"content": response.content,
                             "structural_retry": "previous final object failed" in kwargs["messages"][0].content})
            return response

    catalog = ServerModelCatalogResolver(
        catalog_reader=configured_models,
        model_builder=lambda client, config: ObservedModel(build_model_from_entry(client, config)),
    )
    results = []
    for case in json.loads(cases_path.read_text(encoding="utf-8")):
        commit = TurnCommit.from_dict(case["input"]["commit"])
        captured = case["input"]["context"]
        tasks = tuple(AuthenticatedTaskFact(**{
            **fact, "state": TaskState(fact["state"]),
            "outcome": TerminalOutcome(fact["outcome"]) if fact["outcome"] else None,
            "attempt_state": AttemptState(fact["attempt_state"]),
            "attempt_outcome": TerminalOutcome(fact["attempt_outcome"]) if fact["attempt_outcome"] else None,
            "supported_operations": frozenset(fact["supported_operations"]),
        }) for fact in captured["tasks"])
        context = TaskSemanticContext(TaskAuthorityRead(commit.scope, captured["authority_fingerprint"], tasks),
                                      captured["conversation_id"], tuple(captured["history"]), tuple(captured["pending"]))
        observed.clear()
        row = {"case": case["case"], "passed": False}
        try:
            decision = await TaskSemanticResolver(catalog).resolve(commit, context)
            row.update(route=decision.route, operation=decision.proposal.operation,
                       target=decision.proposal.target, arguments=dict(decision.proposal.arguments))
            expected = case["expected"]
            row["passed"] = all(row.get(key) == value for key, value in expected.items() if key != "adjustment_contains")
            row["passed"] &= all(value in str(row["arguments"].get("adjustment", "")) for value in expected.get("adjustment_contains", []))
        except Exception as error:
            row.update(error=type(error).__name__, reason=getattr(error, "reason", "PROBE_FAILURE"))
            row["cause_type"] = type(error.__cause__).__name__ if error.__cause__ else None
            cause = error
            row["cause_chain"] = []
            while cause is not None:
                row["cause_chain"].append({"type": type(cause).__name__,
                                           "status_code": getattr(cause, "status_code", None)})
                cause = cause.__cause__
            import traceback
            row["cause_frames"] = [f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
                                    for frame in traceback.extract_tb((error.__cause__ or error).__traceback__)[-5:]]
        row["model_calls"] = len(observed)
        row["observed"] = list(observed)
        results.append(row)
        print(json.dumps({key: value for key, value in row.items() if key != "observed"}, ensure_ascii=False), flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "boundary": "configured semantic model only; zero Task/Tool execution",
        "cases_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
        "resolver_sha256": hashlib.sha256(Path("jiuwenswarm/server/live_voice/task_semantics.py").read_bytes()).hexdigest(),
        "results": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return int(not all(row["passed"] for row in results))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.config_dir, args.cases, args.output)))
