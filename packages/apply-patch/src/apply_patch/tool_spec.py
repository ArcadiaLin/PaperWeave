"""给模型看的 apply_patch 工具说明与语法。

原文取自上游 ``src/agents/sandbox/capabilities/tools/apply_patch_tool.py`` 的
``_APPLY_PATCH_CUSTOM_TOOL_GRAMMAR``、``_APPLY_PATCH_CUSTOM_TOOL_DESCRIPTION`` 与
``_APPLY_PATCH_CUSTOM_TOOL_CONFIG``，未改动。说明是面向代码文件写的，用到图视图上时
需要另写我们自己的说明；这里保留原文作为起点。
"""

from __future__ import annotations

from typing import Any

GRAMMAR = r"""
start: begin_patch hunk+ end_patch
begin_patch: "*** Begin Patch" LF
end_patch: "*** End Patch" LF?

hunk: add_hunk | delete_hunk | update_hunk
add_hunk: "*** Add File: " filename LF add_line+
delete_hunk: "*** Delete File: " filename LF
update_hunk: "*** Update File: " filename LF change_move? change

filename: /(.+)/
add_line: "+" /(.*)/ LF -> line

change_move: "*** Move to: " filename LF
change: (change_context | change_line)+ eof_line?
change_context: ("@@" | "@@ " /(.+)/) LF
change_line: ("+" | "-" | " ") /(.*)/ LF
eof_line: "*** End of File" LF

%import common.LF
""".strip()

DESCRIPTION = r"""
Use the `apply_patch` tool to edit files. This is a FREEFORM tool, so do not wrap the patch in JSON.
Your patch language is a stripped-down, file-oriented diff format designed to be easy to
parse and safe to apply. You can think of it as a high-level envelope:

*** Begin Patch
[ one or more file sections ]
*** End Patch

Within that envelope, you get a sequence of file operations.
You MUST include a header to specify the action you are taking.
Each operation starts with one of three headers:

*** Add File: <path> - create a new file. Every following line is a + line (the initial contents).
*** Delete File: <path> - remove an existing file. Nothing follows.
*** Update File: <path> - patch an existing file in place (optionally with a rename).

May be immediately followed by *** Move to: <new path> if you want to rename the file.
Then one or more hunks, each introduced by @@ (optionally followed by a hunk header).
Within a hunk, each line starts with a space, -, or +.

For context lines:
- By default, show 3 lines of code immediately above and 3 lines immediately below each
change. If a change is within 3 lines of a previous change, do NOT duplicate the first
change's post-context lines in the second change's pre-context lines.
- If 3 lines of context is insufficient to uniquely identify the snippet of code within the
file, use the @@ operator to indicate the class or function to which the snippet belongs.
For instance:
@@ class BaseClass
[3 lines of pre-context]
-[old_code]
+[new_code]
[3 lines of post-context]

- If a code block is repeated so many times in a class or function that a single @@ statement
and 3 lines of context cannot uniquely identify the snippet, use multiple @@ statements to
jump to the right context. For instance:

@@ class BaseClass
@@ def method():
[3 lines of pre-context]
-[old_code]
+[new_code]
[3 lines of post-context]

The full grammar definition is below:
Patch := Begin { FileOp } End
Begin := "*** Begin Patch" NEWLINE
End := "*** End Patch" NEWLINE
FileOp := AddFile | DeleteFile | UpdateFile
AddFile := "*** Add File: " path NEWLINE { "+" line NEWLINE }
DeleteFile := "*** Delete File: " path NEWLINE
UpdateFile := "*** Update File: " path NEWLINE [ MoveTo ] Hunk { Hunk }
MoveTo := "*** Move to: " newPath NEWLINE
Hunk := "@@" [ header ] NEWLINE { HunkLine } [ "*** End of File" NEWLINE ]
HunkLine := (" " | "-" | "+") text NEWLINE

A full patch can combine several operations:

*** Begin Patch
*** Add File: hello.txt
+Hello world
*** Update File: src/app.py
*** Move to: src/main.py
@@ def greet():
-print("Hi")
+print("Hello, world!")
*** Delete File: obsolete.txt
*** End Patch

Important:
- You must include a header with your intended action (Add/Delete/Update).
- You must prefix new lines with + even when creating a new file.
- File references can only be relative, NEVER ABSOLUTE.
""".strip()

TOOL_CONFIG: dict[str, Any] = {
    "type": "custom",
    "name": "apply_patch",
    "description": DESCRIPTION,
    "format": {
        "type": "grammar",
        "syntax": "lark",
        "definition": GRAMMAR,
    },
}

__all__ = ["DESCRIPTION", "GRAMMAR", "TOOL_CONFIG"]
