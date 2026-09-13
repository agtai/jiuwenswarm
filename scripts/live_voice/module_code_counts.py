"""Partition an ownership manifest once per file; do not count runtime containers twice."""
import argparse
import json
from pathlib import Path


def module(path):
    name = Path(path).name
    if path.startswith('openjiuwen/'):
        if name in {'contracts.py', 'source.py', '__init__.py', 'execution_control.py', 'execution_observation.py', 'observation.py'}:
            return 'shared'
        if '/durability/' in path or name in {'project_executor.py', 'file_effect_plan.py', 'execution_checkpoint.py', 'executor_capabilities.py'}:
            return 'M7+M9'
        return 'M6+M8'
    if '/frontend/' in path:
        return 'M1+M2'
    if '/gateway/' in path:
        return 'G'
    if '/channels/live_voice/' in path:
        if name in {'openai_realtime_native_engine.py', 'openai_realtime_session.py', 'native_interaction_config.py',
                    'interaction_engine.py', 'batch_speech.py', 'openai_streaming_speech.py', 'streaming_speech.py', 'speech_ports.py'}:
            return 'M3'
        if any(token in name for token in ('diagnostic', 'observability', 'latency')):
            return 'shared'
        return 'M4+M5'
    if '/server/runtime/presentation/' in path:
        return 'M4+M5'
    if '/server/runtime/work/' in path:
        return 'M4+M5' if name == 'native_foreground.py' else 'M6+M8'
    if '/server/runtime/formal_tasks/' in path:
        return 'M7+M9' if name == 'project_code_executor.py' else 'M6+M8'
    if '/server/runtime/agent_adapter/' in path or '/agents/' in path or name in {'execution.py', 'execution_context.py'}:
        return 'M7+M9'
    return 'shared'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text(encoding='utf-8'))
    totals = {}
    for row in data['files']:
        row['module'] = module(row['path'])
        count = totals.setdefault(row['module'], dict(current_lines=0, new_file_lines=0, net_lines=0))
        count['current_lines'] += row['current_lines']
        count['net_lines'] += row['net_lines']
        count['new_file_lines'] += row['current_lines'] if row['new_file'] else 0
    assert sum(r['current_lines'] for r in totals.values()) == sum(r['current_lines'] for r in data['totals'].values())
    data['module_totals'] = totals
    data['module_attribution'] = 'Exclusive primary-responsibility file buckets, not function-level hot-path counts. Shared includes contracts/config/auth/diagnostics/Host wiring. Browser and Gateway include existing shared-file changes; M3 includes retained cascade adapters. Containers and cloud code not counted twice.'
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(totals, indent=2))


if __name__ == '__main__':
    main()
