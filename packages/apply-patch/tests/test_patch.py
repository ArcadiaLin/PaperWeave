"""parse_patch 与内存版 apply_patch 的测试（本包新增，非上游）。"""

from __future__ import annotations

import json

import pytest

from apply_patch import ApplyPatchError, apply_patch, parse_patch, parse_patch_input

VIEW = "nodes:\n  method_0016:\n    name: DLinear\n    aliases: []\n    note: old\n"


def test_parse_patch_splits_three_operation_types() -> None:
    ops = parse_patch(
        "\n".join(
            [
                "*** Begin Patch",
                "*** Add File: a.yml",
                "+x: 1",
                "*** Update File: b.yml",
                "*** Move to: c.yml",
                "@@",
                "-y: 1",
                "+y: 2",
                "*** Delete File: d.yml",
                "*** End Patch",
            ]
        )
    )
    assert [(o.type, o.path, o.move_to) for o in ops] == [
        ("create_file", "a.yml", None),
        ("update_file", "b.yml", "c.yml"),
        ("delete_file", "d.yml", None),
    ]
    assert ops[0].diff == "+x: 1\n"
    assert ops[2].diff is None


@pytest.mark.parametrize(
    "raw",
    [
        "*** Update File: a\n@@\n-x\n+y\n*** End Patch",  # 缺 Begin
        "*** Begin Patch\n*** Update File: a\n@@\n-x\n+y",  # 缺 End
        "*** Begin Patch\n*** End Patch",  # 没有操作
        "*** Begin Patch\n*** Update File: a\n*** End Patch",  # Update 没有 hunk
        "*** Begin Patch\n*** Add File: a\nx\n*** End Patch",  # Add 行缺 +
        "*** Begin Patch\n*** Delete File: a\n-x\n*** End Patch",  # Delete 带 diff
    ],
)
def test_parse_patch_rejects_malformed(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_patch(raw)


def test_parse_patch_input_accepts_json() -> None:
    raw = json.dumps({"operations": [{"type": "delete_file", "path": "a"}]})
    assert [(o.type, o.path) for o in parse_patch_input(raw)] == [("delete_file", "a")]


def test_update_view_text() -> None:
    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: view.yml",
            "@@ method_0016:",
            "     name: DLinear",
            "-    aliases: []",
            "-    note: old",
            "+    aliases: [Decomposition-Linear]",
            "+    note: null",
            "*** End Patch",
        ]
    )
    out = apply_patch({"view.yml": VIEW}, patch)
    assert out["view.yml"] == VIEW.replace("aliases: []", "aliases: [Decomposition-Linear]").replace(
        "note: old", "note: null"
    )


def test_create_move_delete() -> None:
    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Add File: new.yml",
            "+graph-doc: v0.1",
            "+nodes: {}",
            "*** Update File: view.yml",
            "*** Move to: renamed.yml",
            "@@",
            "-    note: old",
            "+    note: new",
            "*** Delete File: gone.yml",
            "*** End Patch",
        ]
    )
    out = apply_patch({"view.yml": VIEW, "gone.yml": "x\n"}, patch)
    assert set(out) == {"new.yml", "renamed.yml"}
    assert out["new.yml"] == "graph-doc: v0.1\nnodes: {}"
    assert "note: new" in out["renamed.yml"]


def test_failure_is_atomic_and_reports_index() -> None:
    texts = {"view.yml": VIEW}
    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: view.yml",
            "@@",
            "-    note: old",
            "+    note: new",
            "*** Update File: view.yml",
            "@@",
            "-    no such line",
            "+    x",
            "*** End Patch",
        ]
    )
    with pytest.raises(ApplyPatchError) as err:
        apply_patch(texts, patch)
    assert err.value.index == 1 and err.value.path == "view.yml"
    assert texts == {"view.yml": VIEW}


@pytest.mark.parametrize(
    "patch",
    [
        "*** Begin Patch\n*** Add File: view.yml\n+x\n*** End Patch",  # 已存在
        "*** Begin Patch\n*** Update File: missing.yml\n@@\n-x\n+y\n*** End Patch",
        "*** Begin Patch\n*** Delete File: missing.yml\n*** End Patch",
    ],
)
def test_existence_rules(patch: str) -> None:
    with pytest.raises(ApplyPatchError):
        apply_patch({"view.yml": VIEW}, patch)
