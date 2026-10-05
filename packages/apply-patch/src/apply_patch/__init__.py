"""apply_patch（V4A diff）的独立实现，vendored 自 openai-agents-python。见 README。"""

from .apply_diff import apply_diff
from .operations import (
    ApplyPatchEditor,
    ApplyPatchOperation,
    ApplyPatchOperationType,
    ApplyPatchResult,
)
from .parser import parse_patch, parse_patch_input, parse_patch_json
from .patch import ApplyPatchError, apply_operations, apply_patch

__all__ = [
    "ApplyPatchEditor",
    "ApplyPatchError",
    "ApplyPatchOperation",
    "ApplyPatchOperationType",
    "ApplyPatchResult",
    "apply_diff",
    "apply_operations",
    "apply_patch",
    "parse_patch",
    "parse_patch_input",
    "parse_patch_json",
]
