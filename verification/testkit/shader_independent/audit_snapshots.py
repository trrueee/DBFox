"""Independent standard-library canonical hash and Pillow native file audit."""
from __future__ import annotations

import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys

from PIL import Image


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main(directory: Path):
    evidence = Path('verification/testkit/shader_independent/evidence')
    proof = read_json(evidence / 'electron-public-snapshots.json')
    audits = []
    for result in proof['results']:
        pages = [(page['parameters'], json.loads(page['raw'])['payload']) for page in result['pages']]
        first = pages[0][1]
        summary, metadata = first['document'], first['metadata']
        document = {'id': summary['id'], 'title': summary['title'], 'schema_version': metadata['schema_version'],
                    'language': metadata['language'], 'preview': metadata['preview']}
        for section, count_field in [('stages', 'stage_count'), ('passes', 'pass_count'), ('uniforms', 'uniform_count'), ('textures', 'texture_count')]:
            document[section] = [item for parameters, page in pages if parameters['section'] == section for item in page['items']]
            assert len(document[section]) == metadata[count_field]
        for stage in document['stages']:
            source = ''.join(page['source'] for parameters, page in pages if parameters['section'] == 'source' and parameters['stage_id'] == stage['id'])
            assert digest(source.encode()) == stage['source_hash'] and len(source.encode()) == stage['source_bytes']
            for name in ['source_hash', 'source_bytes', 'line_count']:
                del stage[name]
            stage['source'] = source
        blobs = []
        for texture in document['textures']:
            raw = b''.join(base64.b64decode(page['texture_bytes']['rgba_base64'], validate=True) for parameters, page in pages if parameters['section'] == 'texture_bytes' and parameters['texture_id'] == texture['id'])
            assert len(raw) == texture['width'] * texture['height'] * 4 and digest(raw) == texture['content_hash']
            blobs.append({'content_hash': texture['content_hash'], 'rgba_base64': base64.b64encode(raw).decode('ascii')})
        canonical = json.dumps({'document': document, 'deleted': summary['deleted']}, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
        assert digest(canonical) == summary['content_hash'], (result['project']['name'], digest(canonical), summary['content_hash'])
        assert sum(len(stage['source'].encode()) for stage in document['stages']) == metadata['source_bytes']
        name = f"shader-{summary['id']}-v{summary['version']}.json"
        native = directory / 'downloads' / name
        file_audit = None
        if native.exists():
            assert read_json(native) == {'document': document, 'textures': blobs}
            file_audit = {'filename': name, 'bytes': native.stat().st_size, 'sha256': digest(native.read_bytes()), 'exact_public_snapshot_equal': True}
        if result['project']['name'] == 'Shader Independent Large QA':
            assert len(document['stages']) == 62 and metadata['source_bytes'] == 424809
            plan = read_json(Path('verification/testkit/shader_independent/plans.json'))['shader-independent-large']
            modules = {operation['title']: operation['source'] for step in plan['steps'] for operation in step.get('arguments', {}).get('operations', []) if operation.get('kind') == 'stage_create'}
            assert len(modules) == 60
            assert all(stage['source'] == modules[stage['title']] for stage in document['stages'][2:])
        if result['project']['name'] == 'Shader Independent Stress QA':
            assert [len(document[key]) for key in ['stages', 'passes', 'uniforms', 'textures']] == [3, 2, 1, 1]
            assert document['uniforms'][0]['value'] == .7
            assert document['passes'][0]['bindings'] == [] and document['passes'][1]['title'] == 'Soft Post'
            assert 'speed=0.55' in document['stages'][1]['source'] and 'speed=0.25' not in document['stages'][1]['source']
        audits.append({'project': result['project']['name'], 'version': summary['version'], 'canonical_hash': digest(canonical),
                       'pages': len(pages), 'page_read_ms': result['elapsedMs'], 'native_json': file_audit})
    multipass = read_json(evidence / 'electron-multipass.json')
    with Image.open(BytesIO(bytes(multipass['pngBytes']))) as image:
        rgba = image.convert('RGBA').tobytes()
        assert image.size == (2, 2) and rgba == bytes([255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 255, 255, 0, 255])
    stress = read_json(evidence / 'electron-stress.json')
    preview = next(item for item in reversed(stress['artifacts']) if item['type'] == 'dbfox.shader.preview')
    filename = f"shader-{preview['payload']['report_id']}.png"
    raw = (directory / 'downloads' / filename).read_bytes()
    with Image.open(BytesIO(raw)) as image:
        pixels = image.convert('RGBA')
        assert image.size == (128, 96)
        assert digest(pixels.tobytes()) == stress['metadata']['payload']['pixel_hash']
        public_png = next(item['png'] for item in proof['results'] if item['project']['name'] == 'Shader Independent Stress QA')
        assert raw == base64.b64decode(public_png['bytes_base64'], validate=True)
        colors = len(pixels.getcolors(128 * 96) or [])
        assert colors > 500, colors
    maximum = read_json(evidence / 'electron-maximum-uniforms.json')
    sample = maximum['sample']['payload']
    assert maximum['activeUniformCount'] == 128
    assert maximum['compiled']['outcome']['compiled'] is True and maximum['rendered']['outcome']['rendered'] is True
    assert maximum['head']['version'] == 24 and maximum['rejected']['status'] == 400
    assert sample['sample_width'] == sample['sample_height'] == 32 and bytes(sample['rgba']) == bytes([127, 0, 0, 255]) * 1024
    assert all(f'uniform float gain{i:03d};' in maximum['generatedSource'] for i in range(128))
    assert '+'.join(f'gain{i:03d}' for i in range(128)) in maximum['generatedSource']
    output = {'snapshots': audits, 'multipass_exact_rgba': rgba.hex(),
              'maximum_uniforms': {'count': 128, 'head': maximum['head'], 'real_gpu_sample_pixels': 1024, 'exact_rgba': [127, 0, 0, 255]},
              'stress_png': {'filename': filename, 'bytes': len(raw), 'sha256': digest(raw), 'unique_colors': colors, 'pixel_sha256': digest(pixels.tobytes()), 'size': list(image.size)}}
    (evidence / 'snapshot-download-audit.json').write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main(Path(sys.argv[1]))
