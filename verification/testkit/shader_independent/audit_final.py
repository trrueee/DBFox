"""Audit the final cold candidate using original public bytes and native files."""
from __future__ import annotations

import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys

from PIL import Image


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main(runtime: Path):
    evidence = Path('verification/testkit/shader_independent/evidence')
    proof = read(evidence / 'electron-final-cold.json')
    snapshots = []
    for item in proof['snapshots']:
        raw = base64.b64decode(item['canonical_base64'], validate=True)
        envelope = json.loads(raw)
        assert raw == json.dumps(envelope, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
        summary = item['summary']['document']
        document = envelope['document']
        assert sha(raw) == summary['content_hash'] and summary['id'] == document['id'] == item['documentId']
        assert item['version'] == summary['version'] and envelope['deleted'] == summary['deleted']
        metadata = item['summary']['metadata']
        for section, count in [('stages', 'stage_count'), ('passes', 'pass_count'), ('uniforms', 'uniform_count'), ('textures', 'texture_count')]:
            assert len(document[section]) == metadata[count]
        assert sum(len(stage['source'].encode()) for stage in document['stages']) == metadata['source_bytes']
        for texture, blob in zip(document['textures'], item['textures'], strict=True):
            pixels = base64.b64decode(blob['rgba_base64'], validate=True)
            assert len(pixels) == texture['width'] * texture['height'] * 4 and sha(pixels) == texture['content_hash'] == blob['content_hash']
        filename = f"shader-{item['documentId']}-v{item['version']}.json"
        native = runtime / 'downloads' / filename
        downloaded = None
        if item['artifactId']:
            assert read(native) == {'document': document, 'textures': item['textures']}
            downloaded = {'filename': filename, 'bytes': native.stat().st_size, 'sha256': sha(native.read_bytes())}
        if item['version'] == 24:
            assert len(document['stages']) == 62 and len(document['uniforms']) == 128
            plan = read(Path('verification/testkit/shader_independent/plans.json'))['shader-independent-large']
            modules = {operation['title']: operation['source'] for step in plan['steps'] for operation in step.get('arguments', {}).get('operations', []) if operation.get('kind') == 'stage_create'}
            assert all(stage['source'] == modules[stage['title']] for stage in document['stages'][2:])
            maximum = read(evidence / 'electron-maximum-uniforms.json')
            assert document['stages'][1]['source'] == maximum['generatedSource']
        snapshots.append({'version': item['version'], 'document_id': item['documentId'], 'canonical_bytes': len(raw), 'canonical_sha256': sha(raw), 'texture_count': len(item['textures']), 'native_json': downloaded})
    conversation = proof['conversation']
    assert conversation['runs'][0]['status'] == 'completed'
    calls = [item for item in conversation['items'] if item['type'] == 'function_call']
    assert len(calls) == 1 and calls[0]['payload']['attempt'] == 1
    report = proof['metadata']['payload']
    assert report['compiled'] is True and report['rendered'] is True and report['version'] == 24
    raw = base64.b64decode(proof['png_base64'], validate=True)
    filename = f"shader-{report['id']}.png"
    assert raw == (runtime / 'downloads' / filename).read_bytes()
    with Image.open(BytesIO(raw)) as image:
        pixels = image.convert('RGBA').tobytes()
        assert image.size == (256, 256) and pixels == bytes([127, 0, 0, 255]) * 65536
        assert sha(pixels) == report['pixel_hash']
    events = [json.loads(line) for line in (runtime / 'download-events.jsonl').read_text(encoding='utf-8').splitlines()]
    for name in [filename, *[item['native_json']['filename'] for item in snapshots if item['native_json']]]:
        event = next(event for event in reversed(events) if event['filename'] == name)
        assert event['state'] == 'completed' and event['receivedBytes'] == event['totalBytes']
    result = {'candidate': proof['candidate'], 'snapshots': snapshots, 'native_load_ms': proof['loadMs'], 'native_read_requests': len(proof['nativeReadSections']),
              'run_id': conversation['runs'][0]['id'], 'one_real_gpu_attempt': True, 'report_elapsed_ms': report['elapsed_ms'],
              'png': {'filename': filename, 'bytes': len(raw), 'sha256': sha(raw), 'pixel_sha256': sha(pixels), 'exact_pixels': 65536}}
    (evidence / 'final-cold-audit.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main(Path(sys.argv[1]))
