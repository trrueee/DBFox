"""Task-owned subprocess: terminate at a real signed owner's commit boundary."""
from __future__ import annotations

import os
from pathlib import Path
import sys

from dbfox_dlc_api import ResourceScopeRef, ToolKey
from engine.runtime_composition import build_attempt_resource_resolver
from engine.tools.runtime import ToolRuntime
from verification.bench.capabilities.dbfox_shader.runtime import ShaderRuntime


def main():
    directory, project, document, identity, phase = sys.argv[1:]
    with ShaderRuntime(Path(directory), existing=True) as runtime:
        owner = next(item.tool for item in runtime.snapshot.tools if item.owner_id == 'dbfox.shader' and item.tool.name == 'shader_modify')
        method = 'save_receipt' if phase == 'before_commit' else 'mutate'
        original = getattr(owner.store, method)

        def crash(*args, **kwargs):
            original(*args, **kwargs)
            os._exit(37)  # No context-manager cleanup: genuine process death.

        setattr(owner.store, method, crash)
        scope = ResourceScopeRef(kind='dbfox.shader.studio', id=project, version=1)
        resources = build_attempt_resource_resolver(snapshot=runtime.snapshot).resolve((scope,))
        ToolRuntime(runtime.registry).invoke(tool_name=runtime.registry.provider_name_for_key(ToolKey(owner_id='dbfox.shader', local_name='shader_modify')),
            raw_input={'document_id': document, 'expected_version': 1, 'operations': [{'kind': 'rename_document', 'title': 'Recovered exactly once'}]},
            request=None, invocation_id=identity, idempotency_key=identity, scope_refs=(scope,), resources=resources)
        raise AssertionError('Crash injection did not execute')


if __name__ == '__main__':
    main()
