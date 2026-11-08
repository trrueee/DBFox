"""Reuse the Director's full workload; exercise it in the real Sidecar GPU path.

Only model stimuli are reused. Scoring remains an independent public evidence
audit, and the human edit is performed by native UI outside the model server.
"""
import copy
import json
from pathlib import Path


def main():
    target = Path('verification/testkit/shader_independent/plans.json')
    plans = json.loads(target.read_text(encoding='utf-8'))
    cases = json.loads(Path('verification/bench/capabilities/dbfox_shader/cases.json').read_text(encoding='utf-8'))['cases']
    for case_id, model in [('coral-plasma-stress', 'shader-independent-stress'), ('large-document', 'shader-independent-large')]:
        original = next(case for case in cases if case['case_id'] == case_id)
        steps = [{'id': 'inventory', 'tool': 'shader_inspect', 'arguments': {'section': 'documents'}}]
        for item in original['steps']:
            step = {key: copy.deepcopy(value) for key, value in item.items() if key in {'id', 'kind', 'tool', 'arguments', 'text'}}
            if step['id'] == 'create':
                step['arguments']['expected_generation'] = '$inventory.studio_generation'
            if step.get('kind') == 'human':
                step = {'id': 'human-pause', 'kind': 'answer', 'text': 'The clarified pass change is committed. Perform the requested human title edit in the Studio, then continue so I can inspect the new revision.'}
            if step['id'] == 'ask':
                steps.append({'id': 'first-compile', 'tool': 'compile', 'arguments': {'document_id': '$document_id', 'expected_version': '$version'}})
                steps.append({'id': 'first-preview', 'tool': 'render_preview', 'requires': [{'path': '$first-compile.compiled', 'equals': True}], 'arguments': {'document_id': '$document_id', 'expected_version': '$version'}})
                step['text'] = '请明确更柔和是颜色、强度还是分辨率；当前版本已获得真实 GPU 编译和预览。'
            steps.append(step)
        steps += [
            {'id': 'final-compile', 'tool': 'compile', 'arguments': {'document_id': '$document_id', 'expected_version': '$version'}},
            {'id': 'final-preview', 'tool': 'render_preview', 'requires': [{'path': '$final-compile.compiled', 'equals': True}], 'arguments': {'document_id': '$document_id', 'expected_version': '$version'}},
            {'id': 'final-inspect', 'tool': 'shader_inspect', 'requires': [{'path': '$final-preview.rendered', 'equals': True}], 'arguments': {'document_id': '$document_id', 'version': '$version', 'section': 'summary'}},
        ]
        plans[model] = {'answer': 'The complete workload is committed; the actual driver compiled and rendered the final fixed revision. Its immutable public report and preview are available.', 'steps': steps}
    target.write_text(json.dumps(plans, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
