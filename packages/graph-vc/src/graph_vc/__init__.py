"""graph_vc：图的统一写入底层与版本记录。见 README。"""

from .changeset import RESERVED_LABELS, RESERVED_TYPES, Changeset, EdgeChange, EdgeKey, FileRef, NodeChange
from .errors import ChangesetError, Conflict, ConflictError, FileIntegrityError, GraphVCError
from .state import GraphState, NodeState, check_preconditions
from .store import CommitRecord, VersionedGraph, sha256_file

__all__ = [
    "RESERVED_LABELS",
    "RESERVED_TYPES",
    "Changeset",
    "ChangesetError",
    "CommitRecord",
    "Conflict",
    "ConflictError",
    "EdgeChange",
    "EdgeKey",
    "FileIntegrityError",
    "FileRef",
    "GraphState",
    "GraphVCError",
    "NodeChange",
    "NodeState",
    "VersionedGraph",
    "check_preconditions",
    "sha256_file",
]
