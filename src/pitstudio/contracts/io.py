"""Strict loaders and the deterministic writer for contract documents (FR-001-05, -06, -07).

Every hostile class of data-model 1.4 is rejected with a ``ContractError`` that names the file and the line or the
JSON pointer; a rejected document returns no partial object.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, ClassVar

import yaml

MAX_DEPTH = 32
DEFAULT_MAX_BYTES = 8_388_608  # the largest document cap of data-model 1.4 (the web index)
_BOMS = (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?")
_WS = " \t\n\r"
_STRING_DECODER = json.JSONDecoder()


class ContractError(ValueError):
    """A contract document or value was rejected. ``str()`` names the file and the line or the JSON pointer."""

    def __init__(
        self,
        message: str,
        *,
        file: str | None = None,
        line: int | None = None,
        pointer: str | None = None,
        error_class: str | None = None,
    ) -> None:
        where = [file] if file else []
        if line is not None:
            where.append(f"line {line}")
        if pointer is not None:
            where.append(f"pointer {pointer or '/'}")
        text = f"{': '.join(where)}: {message}" if where else message
        super().__init__(text[:300])
        self.reason = message
        self.file, self.line, self.pointer, self.error_class = file, line, pointer, error_class


def pointer_of(parts: list[Any]) -> str:
    """RFC 6901 JSON pointer of a path (the empty path is the empty string)."""
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def _read(path: Path, max_bytes: int | None) -> tuple[bytes, str]:
    path = Path(path)
    name = path.name
    cap = DEFAULT_MAX_BYTES if max_bytes is None else max_bytes
    try:
        size = path.stat().st_size
        if size > cap:
            raise ContractError(f"{size} bytes exceed the cap of {cap} bytes", file=name)
        data = path.read_bytes()
    except OSError as exc:
        raise ContractError(f"cannot read the file ({exc.strerror or type(exc).__name__})", file=name) from None
    if len(data) > cap:
        raise ContractError(f"{len(data)} bytes exceed the cap of {cap} bytes", file=name)
    if data.startswith(_BOMS):
        raise ContractError("a byte-order mark is not allowed", file=name, line=1)
    return data, name


def _decode(data: bytes, name: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        line = data.count(b"\n", 0, exc.start) + 1
        raise ContractError("invalid UTF-8", file=name, line=line) from None


# ----------------------------------------------------------------------------------------------------------------
# JSON
# ----------------------------------------------------------------------------------------------------------------
class _Reject(Exception):
    """Raised inside the fast parse; the diagnostic pass then finds the location."""


def _no_constant(token: str) -> Any:
    raise _Reject(token)


def _finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise _Reject(token)
    return value


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise _Reject(key)
        out[key] = value
    return out


def _depth(value: Any) -> int:
    best, stack = 0, [(value, 1)]
    while stack:
        node, level = stack.pop()
        if isinstance(node, dict):
            best = max(best, level)
            stack.extend((v, level + 1) for v in node.values())
        elif isinstance(node, list):
            best = max(best, level)
            stack.extend((v, level + 1) for v in node)
    return best


class _Locate:
    """Diagnostic recursive-descent pass over text the fast parse rejected: first defect with line and pointer."""

    def __init__(self, text: str) -> None:
        self.text, self.pos = text, 0

    def line(self, pos: int | None = None) -> int:
        return self.text.count("\n", 0, self.pos if pos is None else pos) + 1

    def fail(self, message: str, pointer: list[Any] | None = None, pos: int | None = None) -> Any:
        raise ContractError(message, line=self.line(pos), pointer=None if pointer is None else pointer_of(pointer))

    def ws(self) -> None:
        text, n = self.text, len(self.text)
        while self.pos < n and text[self.pos] in _WS:
            self.pos += 1

    def value(self, path: list[Any], depth: int) -> None:
        self.ws()
        if self.pos >= len(self.text):
            self.fail("unexpected end of document", path)
        ch = self.text[self.pos]
        if ch in "[{":
            if depth + 1 > MAX_DEPTH:
                self.fail(f"nesting deeper than {MAX_DEPTH} levels", path)
            (self.array if ch == "[" else self.obj)(path, depth + 1)
        elif ch == '"':
            self.string()
        else:
            self.scalar(path)

    def string(self) -> str:
        try:
            value, end = _STRING_DECODER.raw_decode(self.text, self.pos)
        except json.JSONDecodeError as exc:
            self.fail(exc.msg, pos=exc.pos)
        self.pos = end
        return value

    def scalar(self, path: list[Any]) -> None:
        text, start = self.text, self.pos
        for token in ("NaN", "Infinity", "-Infinity"):
            if text.startswith(token, start):
                self.fail(f"non-finite number {token}", path, start)
        m = _NUMBER.match(text, start)
        if m:
            token = m.group(0)
            if not math.isfinite(float(token)):
                self.fail(f"non-finite number {token}", path, start)
            self.pos = m.end()
            return
        for word in ("true", "false", "null"):
            if text.startswith(word, start):
                self.pos = start + len(word)
                return
        self.fail("invalid value", path, start)

    def array(self, path: list[Any], depth: int) -> None:
        self.pos += 1
        self.ws()
        if self.text.startswith("]", self.pos):
            self.pos += 1
            return
        index = 0
        while True:
            self.value([*path, index], depth)
            self.ws()
            if self.text.startswith(",", self.pos):
                self.pos += 1
                index += 1
                continue
            if self.text.startswith("]", self.pos):
                self.pos += 1
                return
            self.fail("expected ',' or ']'", path)

    def obj(self, path: list[Any], depth: int) -> None:
        self.pos += 1
        self.ws()
        if self.text.startswith("}", self.pos):
            self.pos += 1
            return
        seen: set[str] = set()
        while True:
            self.ws()
            if not self.text.startswith('"', self.pos):
                self.fail("expected a string key", path)
            key_pos = self.pos
            key = self.string()
            if key in seen:
                self.fail("duplicate key", [*path, key], key_pos)
            seen.add(key)
            self.ws()
            if not self.text.startswith(":", self.pos):
                self.fail("expected ':'", [*path, key])
            self.pos += 1
            self.value([*path, key], depth)
            self.ws()
            if self.text.startswith(",", self.pos):
                self.pos += 1
                continue
            if self.text.startswith("}", self.pos):
                self.pos += 1
                return
            self.fail("expected ',' or '}'", path)


def parse_json_text(text: str, name: str = "<text>") -> Any:
    """Strict parse of JSON text (see ``load_json``); ``name`` is the file name used in errors."""
    try:
        value = json.loads(
            text, parse_constant=_no_constant, parse_float=_finite_float, object_pairs_hook=_no_duplicates
        )
        if _depth(value) > MAX_DEPTH:
            raise _Reject("depth")
    except _Reject, RecursionError:
        try:
            locator = _Locate(text)
            locator.value([], 0)
            locator.ws()
            if locator.pos < len(text):
                locator.fail("extra data after the document")
        except ContractError as exc:
            raise ContractError(
                exc.reason, file=name, line=exc.line, pointer=exc.pointer, error_class=exc.error_class
            ) from None
        raise ContractError("rejected document", file=name) from None  # pragma: no cover - diagnostic found nothing
    except json.JSONDecodeError as exc:
        raise ContractError(exc.msg, file=name, line=exc.lineno) from None
    except ValueError as exc:  # e.g. an integer literal over the interpreter's digit limit
        raise ContractError(str(exc), file=name) from None
    return value


def load_json(path: Path, *, max_bytes: int | None = None) -> Any:
    """Load a JSON contract document: size cap, UTF-8 without BOM, finite numbers, unique keys, depth <= 32."""
    data, name = _read(path, max_bytes)
    return parse_json_text(_decode(data, name), name)


# ----------------------------------------------------------------------------------------------------------------
# YAML
# ----------------------------------------------------------------------------------------------------------------
_STR_TAG = "tag:yaml.org,2002:str"


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader without anchors, aliases, tags, merge keys, implicit dates and YAML 1.1 booleans."""

    yaml_implicit_resolvers: ClassVar[dict[str, list[Any]]] = {  # type: ignore[misc]
        first: [(tag, rx) for tag, rx in rules if tag not in ("tag:yaml.org,2002:bool", "tag:yaml.org,2002:timestamp")]
        for first, rules in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }

    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self._depth = 0

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.AliasEvent):
            raise ContractError("anchors and aliases are not allowed", line=self.peek_event().start_mark.line + 1)
        event = self.peek_event()
        line = event.start_mark.line + 1
        if event.anchor is not None:
            raise ContractError("anchors and aliases are not allowed", line=line)
        if getattr(event, "tag", None) is not None:
            raise ContractError("explicit tags are not allowed", line=line)
        nested = isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent))
        if nested:
            self._depth += 1
            if self._depth > MAX_DEPTH:
                raise ContractError(f"nesting deeper than {MAX_DEPTH} levels", line=line)
        node = super().compose_node(parent, index)
        if nested:
            self._depth -= 1
        return node

    def construct_mapping(self, node: Any, deep: bool = False) -> dict[Any, Any]:
        out: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            line = key_node.start_mark.line + 1
            if key_node.tag != _STR_TAG:
                raise ContractError("mapping keys must be strings", line=line)
            key = self.construct_object(key_node, deep=True)
            if key in out:
                raise ContractError("duplicate key", line=line, pointer=pointer_of([key]))
            out[key] = self.construct_object(value_node, deep=deep)
        return out

    def construct_yaml_float(self, node: Any) -> float:
        value = super().construct_yaml_float(node)
        if not math.isfinite(value):
            raise ContractError("non-finite number", line=node.start_mark.line + 1)
        return value


_StrictLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF")
)
_StrictLoader.add_constructor("tag:yaml.org,2002:float", _StrictLoader.construct_yaml_float)  # type: ignore[type-var]
_StrictLoader.add_constructor("tag:yaml.org,2002:map", _StrictLoader.construct_yaml_map)  # type: ignore[type-var]


def load_yaml(path: Path, *, max_bytes: int | None = None) -> Any:
    """Load a YAML contract document: one document, no anchors, tags or duplicate keys, strict scalars (FR-001-06)."""
    data, name = _read(path, max_bytes)
    text = _decode(data, name)
    loader = _StrictLoader(text)
    try:
        return loader.get_single_data()
    except ContractError as exc:
        raise ContractError(exc.reason, file=name, line=exc.line, pointer=exc.pointer) from None
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        reason = getattr(exc, "problem", None) or "invalid YAML"
        if isinstance(exc, yaml.composer.ComposerError) and "single document" in str(reason):
            reason = "more than one YAML document"
        raise ContractError(str(reason), file=name, line=None if mark is None else mark.line + 1) from None
    except RecursionError:
        raise ContractError(f"nesting deeper than {MAX_DEPTH} levels", file=name) from None
    finally:
        loader.dispose()


# ----------------------------------------------------------------------------------------------------------------
# writer
# ----------------------------------------------------------------------------------------------------------------
def dump_json(obj: Any) -> bytes:
    """The one contract writer: UTF-8, no BOM, LF, 2-space indent, trailing newline, no NaN or Infinity."""
    try:
        text = json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False)
        return (text + "\n").encode("utf-8")
    except (ValueError, UnicodeEncodeError) as exc:
        raise ContractError(str(exc)) from None
