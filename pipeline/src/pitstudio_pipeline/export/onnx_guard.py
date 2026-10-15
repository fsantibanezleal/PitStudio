"""The single choke point every consumer calls before reading an ONNX file (FR-016-03).

A file that does not parse as a ModelProto, has `ir_version` > 10, references external data outside its own folder or is
2**31 bytes or larger is rejected with the reason, and nothing is read from it beyond the protobuf header.
"""

from __future__ import annotations

import hashlib
import ntpath
import posixpath
from dataclasses import dataclass
from pathlib import Path

MAX_IR_VERSION = 10
SIZE_LIMIT = 2**31


class OnnxFileRejected(Exception):
    """A hostile or unusable ONNX file; `.reason` is the message."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class OnnxFileInfo:
    ir_version: int
    nbytes: int
    sha256: str


def _escapes(location: str, folder: Path) -> bool:
    normal = location.replace("\\", "/")
    if posixpath.isabs(normal) or ntpath.isabs(location) or ntpath.splitdrive(location)[0] or "\x00" in normal:
        return True
    resolved = (folder / normal).resolve()
    return not resolved.is_relative_to(folder.resolve())


def check_onnx_file(path: Path, *, size_bytes: int | None = None) -> OnnxFileInfo:
    """Return the facts of an acceptable file; raise OnnxFileRejected otherwise. `size_bytes` overrides the file size."""
    import onnx

    path = Path(path)
    if not path.is_file():
        raise OnnxFileRejected(f"{path.name}: not a file")
    nbytes = path.stat().st_size if size_bytes is None else size_bytes
    if nbytes >= SIZE_LIMIT:
        raise OnnxFileRejected(f"{path.name}: size {nbytes} bytes is 2**31 or more")
    data = path.read_bytes()
    try:
        model = onnx.load_from_string(data)
    except Exception as exc:
        raise OnnxFileRejected(f"{path.name}: does not parse as an ONNX ModelProto ({type(exc).__name__})") from exc
    if not data or model.ir_version == 0:
        raise OnnxFileRejected(f"{path.name}: does not parse as an ONNX ModelProto (no ir_version)")
    if model.ir_version > MAX_IR_VERSION:
        raise OnnxFileRejected(f"{path.name}: ir_version {model.ir_version} is above {MAX_IR_VERSION}")
    for tensor in model.graph.initializer:
        if tensor.data_location != onnx.TensorProto.EXTERNAL:
            continue
        for entry in tensor.external_data:
            if entry.key == "location" and _escapes(entry.value, path.parent):
                raise OnnxFileRejected(f"{path.name}: external data location {entry.value!r} leaves the model folder")
    return OnnxFileInfo(model.ir_version, nbytes, hashlib.sha256(data).hexdigest())
