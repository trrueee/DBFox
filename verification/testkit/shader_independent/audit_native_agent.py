"""Audit durable public RunItems independently of the scripted model's assertions."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    folder = Path('verification/testkit/shader_independent/evidence')
    proof = json.loads((folder / 'electron-native-agent-fixed.json').read_text(encoding='utf-8'))
    run = next(run for run in proof['final']['runs'] if run['id'] == proof['admitted']['run_id'])
    assert run['status'] == 'completed' and run['error'] is None
    assert proof['shaderDockCount'] == 0
    calls = [item['payload'] for item in proof['final']['items'] if item['type'] == 'function_call']
    outputs = {item['payload']['call_id']: json.loads(item['payload']['output'])
               for item in proof['final']['items'] if item['type'] == 'function_call_output'}
    assert len(calls) == len(outputs) == 9
    assert all(item['attempt'] == 1 for item in calls)
    assert all(item['status'] == 'succeeded' for item in outputs.values())
    assert [item['call_id'] for item in calls] == [
        'inventory', 'create', 'invalid', 'broken_compile', 'diagnostics', 'repair', 'compiled', 'preview', 'export']
    facts = {key: value['facts'] for key, value in outputs.items()}
    assert facts['broken_compile']['compiled'] is False
    diagnostic = next(item for item in facts['diagnostics']['items'] if item['code'] == 'GLSL_DIAGNOSTIC')
    assert diagnostic['line'] == 4 and 'BROKEN_TOKEN' in diagnostic['message']
    assert diagnostic['stage_id'] == facts['create']['created_refs']['fragment']
    assert facts['compiled']['compiled'] is True and facts['preview']['rendered'] is True
    assert [facts[key]['document']['version'] for key in ['create', 'invalid', 'repair', 'export']] == [1, 2, 3, 3]
    repair = next(item for item in calls if item['call_id'] == 'repair')['arguments']['operations']
    assert repair == [{'kind': 'stage_patch', 'stage_id': {'id': facts['create']['created_refs']['fragment']},
                       'old_text': ' BROKEN_TOKEN', 'new_text': ''}]
    assert len(proof['artifacts']) == 8
    result = {'run_id': run['id'], 'status': run['status'], 'native_calls': 9, 'all_attempts': 1,
              'shader_dock_count': 0, 'elapsed_ms': proof['elapsedMs'], 'artifact_count': 8,
              'actual_driver_diagnostic': diagnostic, 'repair_operations': repair,
              'compile_report': facts['compiled'], 'preview_report': facts['preview']}
    (folder / 'native-agent-audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'native_calls': 9, 'status': run['status'], 'elapsed_ms': proof['elapsedMs']}))


if __name__ == '__main__':
    main()
