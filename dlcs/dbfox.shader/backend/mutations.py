"""One bounded typed edit batch, validated once against its final document."""
from __future__ import annotations

import base64
from hashlib import sha256
from uuid import uuid4

from . import contracts as c


DEFAULT_VERTEX = "#version 300 es\nvoid main() {\n  vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);\n  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);\n}\n"
DEFAULT_FRAGMENT = "#version 300 es\nprecision highp float;\nuniform vec2 u_resolution;\nout vec4 color;\nvoid main() {\n  vec2 uv = gl_FragCoord.xy / u_resolution;\n  color = vec4(uv, 0.5, 1.0);\n}\n"


def new_document(title: str) -> tuple[c.Document, dict[str, str]]:
    ids = {name: str(uuid4()) for name in ("vertex", "fragment", "pass")}
    doc = c.Document(id=str(uuid4()), title=title, stages=[
        c.Stage(id=ids["vertex"], title="Fullscreen triangle", kind="vertex", source=DEFAULT_VERTEX),
        c.Stage(id=ids["fragment"], title="Gradient", kind="fragment", source=DEFAULT_FRAGMENT)],
        passes=[c.Pass(id=ids["pass"], title="Main", vertex_stage_id=ids["vertex"], fragment_stage_id=ids["fragment"], width=256, height=256, clear_color=[0., 0., 0., 1.])],
        preview=c.Preview(pass_id=ids["pass"], width=256, height=256, time_seconds=0.))
    return doc, ids


def decode_rgba(value: str, width: int, height: int) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise ValueError("Invalid strict RGBA base64") from exc
    if len(raw) != width * height * 4 or base64.b64encode(raw).decode("ascii") != value:
        raise ValueError("RGBA length or canonical base64 mismatch")
    return raw


def dedicated_operations(data: c.UniformSetInput | c.TextureBindInput | c.PassCreateInput) -> list[c.Operation]:
    if isinstance(data, c.UniformSetInput):
        return [c.UniformUpdate(kind="uniform_update", uniform_id=c.ObjectId(id=data.uniform_id), value=data.value)]

    def selected(binding: c.Binding) -> c.BindingInput:
        if isinstance(binding.source, c.TextureSource):
            source = c.SelectTextureSource(kind="texture", texture_id=c.ObjectId(id=binding.source.texture_id))
        else:
            source = c.SelectPassSource(kind="pass", pass_id=c.ObjectId(id=binding.source.pass_id))
        return c.BindingInput(name=binding.name, source=source, filter=binding.filter, wrap=binding.wrap)

    if isinstance(data, c.TextureBindInput):
        value = selected(c.Binding(name=data.name, source=data.source, filter=data.filter, wrap=data.wrap))
        return [c.BindingSet(kind="binding_set", pass_id=c.ObjectId(id=data.pass_id), name=value.name, source=value.source, filter=value.filter, wrap=value.wrap)]
    return [c.PassCreate(kind="pass_create", ref="pass", title=data.title, vertex_stage_id=c.ObjectId(id=data.vertex_stage_id), fragment_stage_id=c.ObjectId(id=data.fragment_stage_id), width=data.width, height=data.height, clear_color=data.clear_color, bindings=[selected(value) for value in data.bindings])]


def apply_operations(original: c.Document, operations: list[c.Operation]) -> tuple[c.Document, dict[str, str], dict[str, bytes], list[str]]:
    doc = original.model_copy(deep=True)
    refs: dict[str, str] = {}
    blobs: dict[str, bytes] = {}
    generated: list[str] = []

    def identity(selector: c.ObjectSelector) -> str:
        if isinstance(selector, c.ObjectId):
            return selector.id
        if selector.ref not in refs:
            raise ValueError("Local ref must name an earlier create in this batch")
        return refs[selector.ref]

    def create_id(op: c.CreateObject) -> str:
        value = str(uuid4())
        generated.append(value)
        if op.ref is not None:
            if op.ref in refs:
                raise ValueError("Duplicate local ref")
            refs[op.ref] = value
        return value

    def binding(value: c.BindingInput) -> c.Binding:
        source: c.BindingSource
        if isinstance(value.source, c.SelectTextureSource):
            source = c.TextureSource(kind="texture", texture_id=identity(value.source.texture_id))
        else:
            source = c.PassSource(kind="pass", pass_id=identity(value.source.pass_id))
        return c.Binding(name=value.name, source=source, filter=value.filter, wrap=value.wrap)

    def index(items: list[c.Stage] | list[c.Pass] | list[c.Uniform] | list[c.Texture], target: str) -> int:
        for number, item in enumerate(items):
            if item.id == target:
                return number
        raise ValueError("Object does not exist in this document")

    for op in operations:
        if isinstance(op, c.RenameDocument):
            doc.title = op.title
        elif isinstance(op, c.StageCreate):
            doc.stages.append(c.Stage(id=create_id(op), kind=op.stage_kind, title=op.title, source=op.source))
        elif isinstance(op, (c.StageReplace, c.StagePatch)):
            item = doc.stages[index(doc.stages, identity(op.stage_id))]
            if isinstance(op, c.StageReplace):
                item.source = op.source
            else:
                if item.source.count(op.old_text) != 1:
                    raise ValueError("stage_patch old_text must occur exactly once")
                item.source = item.source.replace(op.old_text, op.new_text, 1)
        elif isinstance(op, c.StageRemove):
            doc.stages.pop(index(doc.stages, identity(op.stage_id)))
        elif isinstance(op, c.PassCreate):
            # Resolve refs before registering this create: self-ref is never valid.
            vertex, fragment = identity(op.vertex_stage_id), identity(op.fragment_stage_id)
            bindings = [binding(value) for value in op.bindings]
            doc.passes.append(c.Pass(id=create_id(op), title=op.title, vertex_stage_id=vertex, fragment_stage_id=fragment, width=op.width, height=op.height, clear_color=op.clear_color, bindings=bindings))
        elif isinstance(op, c.PassUpdate):
            item_pass = doc.passes[index(doc.passes, identity(op.pass_id))]
            changes = op.model_dump(exclude_none=True, exclude={"kind", "pass_id", "vertex_stage_id", "fragment_stage_id"})
            if op.vertex_stage_id is not None:
                changes["vertex_stage_id"] = identity(op.vertex_stage_id)
            if op.fragment_stage_id is not None:
                changes["fragment_stage_id"] = identity(op.fragment_stage_id)
            doc.passes[index(doc.passes, item_pass.id)] = item_pass.model_copy(update=changes)
        elif isinstance(op, c.PassRemove):
            doc.passes.pop(index(doc.passes, identity(op.pass_id)))
        elif isinstance(op, c.PassReorder):
            ids = [identity(value) for value in op.pass_ids]
            if len(ids) != len(set(ids)) or set(ids) != {value.id for value in doc.passes}:
                raise ValueError("pass_reorder requires an exact permutation")
            doc.passes = [doc.passes[index(doc.passes, value)] for value in ids]
        elif isinstance(op, c.UniformCreate):
            pass_id = identity(op.pass_id)
            doc.uniforms.append(c.Uniform(id=create_id(op), pass_id=pass_id, name=op.name, type=op.type, value=op.value))
        elif isinstance(op, c.UniformUpdate):
            position = index(doc.uniforms, identity(op.uniform_id))
            changes = op.model_dump(exclude_none=True, exclude={"kind", "uniform_id", "pass_id"})
            if op.pass_id is not None:
                changes["pass_id"] = identity(op.pass_id)
            doc.uniforms[position] = doc.uniforms[position].model_copy(update=changes)
        elif isinstance(op, c.UniformRemove):
            doc.uniforms.pop(index(doc.uniforms, identity(op.uniform_id)))
        elif isinstance(op, c.BindingSet):
            item_pass = doc.passes[index(doc.passes, identity(op.pass_id))]
            value_binding = binding(op)
            item_pass.bindings = [value for value in item_pass.bindings if value.name != op.name] + [value_binding]
        elif isinstance(op, c.BindingRemove):
            item_pass = doc.passes[index(doc.passes, identity(op.pass_id))]
            if not any(value.name == op.name for value in item_pass.bindings):
                raise ValueError("Binding does not exist")
            item_pass.bindings = [value for value in item_pass.bindings if value.name != op.name]
        elif isinstance(op, c.TextureCreate):
            raw = decode_rgba(op.rgba_base64, op.width, op.height)
            digest = sha256(raw).hexdigest()
            blobs[digest] = raw
            doc.textures.append(c.Texture(id=create_id(op), title=op.title, width=op.width, height=op.height, content_hash=digest))
        elif isinstance(op, c.TextureRemove):
            doc.textures.pop(index(doc.textures, identity(op.texture_id)))
        elif isinstance(op, c.PreviewSet):
            changes = op.model_dump(exclude_none=True, exclude={"kind", "pass_id"})
            if op.pass_id is not None:
                changes["pass_id"] = identity(op.pass_id)
            doc.preview = doc.preview.model_copy(update=changes)
    # Round trip deliberately revalidates model_copy edits and final references.
    return c.Document.model_validate(doc.model_dump(mode="json")), refs, blobs, generated
