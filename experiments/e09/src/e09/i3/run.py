"""I3 首个实例的运行器：三组（S、S-Cypher、R0）× 问题 × 重复，每次一个新的 pi 会话。

    python -m e09.i3.run run --questions Q1 --arms S,S-Cypher,R0 --label pilot   # 批量运行
    python -m e09.i3.run shell S                                                 # 以同样配置打开交互式 pi，调试用

pi 的命令只在这里构造（pi-configs/i3-audit/start.sh 也调用 shell 子命令），保证三组除工具与材料外一切相同：
- system prompt：SYSTEM.md；S 与 S-Cypher 追加 DATA_MODEL.md，S-Cypher 再追加 SCHEMA_CYPHER.md；
  R0 追加两篇论文全文（与入库材料是同一份文件）。
- 用户消息：questions.yml 的 instructions、answer_format 与一道题，三组逐字相同。
- 工具：extensions/i3-tools.ts 按 I3_ARM 注册（S：四个算子；S-Cypher：cypher 与 read_evidence；R0：无）。

每次运行写到 data/processed/e09-i3/<run_id>/：manifest.json（出处与逐会话统计）、prompts/（实际用到的
system prompt 附件）、answers/（最终回答原文）、events/（pi 的 JSON 事件流）。会话 JSONL 原样留在
pi-configs/i3-audit/sessions/<arm>/，manifest 记录路径，并复制一份到 sessions/，使运行目录自足。
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..config import PAPERS, REPO
from ..utils.graph import driver, q

CONFIG = REPO / "pi-configs/i3-audit"
I3 = REPO / "experiments/e09/i3"
OUT = REPO / "data/processed/e09-i3"
PYTHON = REPO / ".venv/bin/python"
MODEL = "sglang/qwen3.8-27b"
ARMS = ("S", "S-Cypher", "R0")
PAPER_FILES = {"dlinear": PAPERS / "2023-DLinear/paper.md", "patchtst": PAPERS / "2023-PatchTST/paper.md"}
TIMEOUT = 3600   # 单个会话的上限（秒）


def load_questions() -> dict:
    return yaml.safe_load((I3 / "questions.yml").read_text(encoding="utf-8"))


def user_message(qs: dict, question: dict) -> str:
    return (f"{qs['instructions'].strip()}\n\n{qs['answer_format'].strip()}\n\n"
            f"Question {question['id']}: {question['text'].strip()}")


def papers_prompt(dest: Path) -> Path:
    """R0 的材料：两篇论文全文，各加一行标题说明它在答案中的键。"""
    parts = [f"# Paper `{key}`\n\nThe full text of the paper `{key}` follows.\n\n{path.read_text(encoding='utf-8')}"
             for key, path in PAPER_FILES.items()]
    dest.write_text("\n\n".join(parts), encoding="utf-8")
    return dest


def pi_command(arm: str, session_dir: Path, prompts: Path, thinking: str) -> tuple[list[str], dict]:
    appends = {"S": ["DATA_MODEL.md"], "S-Cypher": ["DATA_MODEL.md", "SCHEMA_CYPHER.md"], "R0": []}[arm]
    files = [CONFIG / a for a in appends]
    if arm == "R0":
        files.append(papers_prompt(prompts / "R0-papers.md"))
    cmd = ["pi", "--system-prompt", str(CONFIG / "SYSTEM.md")]
    for f in files:
        cmd += ["--append-system-prompt", str(f)]
    cmd += ["--session-dir", str(session_dir), "--model", MODEL, "--thinking", thinking,
            "--no-builtin-tools", "--no-context-files", "--no-skills", "--no-prompt-templates", "--no-themes",
            "--no-extensions", "--extension", str(CONFIG), "--offline"]
    env = {**os.environ, "PI_CODING_AGENT_DIR": str(CONFIG / "agent"), "I3_ARM": arm,
           "I3_PYTHON": str(PYTHON), "I3_REPO": str(REPO)}
    return cmd, env


def session_stats(path: Path) -> dict:
    """从会话 JSONL 统计 token、轮数与工具调用；取最后一条 assistant 文本作为回答。"""
    usage = {"input": 0, "output": 0, "cacheRead": 0, "totalTokens": 0}
    tools, turns, answer, errors, lines_read = {}, 0, "", 0, 0
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if entry.get("type") != "message":
            continue
        m = entry["message"]
        if m.get("role") == "assistant":
            turns += 1
            for k in usage:
                usage[k] += (m.get("usage") or {}).get(k, 0)
            texts = [c.get("text", "") for c in m.get("content") or [] if c.get("type") == "text"]
            for c in m.get("content") or []:
                if c.get("type") == "toolCall":
                    tools[c.get("name")] = tools.get(c.get("name"), 0) + 1
            if texts and "".join(texts).strip():
                answer = "".join(texts)
        elif m.get("role") == "toolResult":
            errors += bool(m.get("isError"))
            if m.get("toolName") == "read_evidence" and not m.get("isError"):
                try:
                    lines_read += json.loads(m["content"][0]["text"])["coverage"]["lines"]
                except (KeyError, IndexError, ValueError, TypeError):
                    pass
    return {"usage": usage, "assistant_turns": turns, "tool_calls": tools, "tool_errors": errors,
            "evidence_lines_read": lines_read, "answer": answer}


def git_state() -> dict:
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "experiments/e09", "pi-configs/i3-audit"],
                           cwd=REPO, capture_output=True, text=True).stdout.strip()
    return {"commit": sha, "dirty_paths": dirty.splitlines()}


def run(args) -> int:
    qs = load_questions()
    wanted = args.questions.split(",") if args.questions else [x["id"] for x in qs["questions"]]
    questions = [x for x in qs["questions"] if x["id"] in wanted]
    if missing := set(wanted) - {x["id"] for x in questions}:
        print(f"未知问题 {sorted(missing)}", file=sys.stderr)
        return 2
    arms = args.arms.split(",")
    if bad := set(arms) - set(ARMS):
        print(f"未知组别 {sorted(bad)}", file=sys.stderr)
        return 2
    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{args.label}"
    out = OUT / run_id
    for sub in ("prompts", "answers", "events", "sessions"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    snapshot = q("MATCH (b:IngestBatch) RETURN b.id AS id ORDER BY id DESC LIMIT 1")[0]["id"]
    driver.close()
    version = subprocess.run(["pi", "--version"], capture_output=True, text=True).stdout.strip()
    manifest = {"run_id": run_id, "created_at": datetime.now(timezone.utc).isoformat(), "git": git_state(),
                "store_snapshot": snapshot, "pi_version": version, "model": MODEL, "thinking": args.thinking,
                "questions_version": qs["version"], "arms": arms, "questions": [x["id"] for x in questions],
                "repeats": args.repeats, "sessions": []}
    for f in ("SYSTEM.md", "DATA_MODEL.md", "SCHEMA_CYPHER.md"):
        shutil.copy(CONFIG / f, out / "prompts" / f)
    (out / "prompts/questions.yml").write_text((I3 / "questions.yml").read_text(encoding="utf-8"), encoding="utf-8")

    for rep in range(1, args.repeats + 1):
        for question in questions:
            for arm in arms:
                session_dir = CONFIG / "sessions" / arm
                session_dir.mkdir(parents=True, exist_ok=True)
                before = set(session_dir.glob("*.jsonl"))
                cmd, env = pi_command(arm, session_dir, out / "prompts", args.thinking)
                tag = f"{arm}__{question['id']}__r{rep}"
                print(f"[{datetime.now():%H:%M:%S}] {tag} …", flush=True)
                t0 = time.monotonic()
                with open(out / "events" / f"{tag}.jsonl", "w", encoding="utf-8") as events:
                    try:
                        proc = subprocess.run(cmd + ["-p", "--mode", "json", user_message(qs, question)], env=env,
                                              cwd=REPO, stdout=events, stderr=subprocess.PIPE, text=True, timeout=TIMEOUT)
                        code, stderr = proc.returncode, proc.stderr
                    except subprocess.TimeoutExpired:
                        code, stderr = "timeout", ""
                seconds = round(time.monotonic() - t0, 1)
                new = sorted(set(session_dir.glob("*.jsonl")) - before)
                record = {"arm": arm, "question": question["id"], "repeat": rep, "exit": code, "seconds": seconds,
                          "stderr": stderr[-2000:], "session": str(new[-1].relative_to(REPO)) if new else None}
                if new:
                    shutil.copy(new[-1], out / "sessions" / f"{tag}.jsonl")
                    stats = session_stats(new[-1])
                    (out / "answers" / f"{tag}.md").write_text(stats.pop("answer"), encoding="utf-8")
                    record |= stats
                manifest["sessions"].append(record)
                (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"    exit={code} {seconds}s tokens={record.get('usage', {}).get('totalTokens')} "
                      f"tools={record.get('tool_calls')}", flush=True)
    print(f"→ {out.relative_to(REPO)}")
    return 0


def shell(args) -> int:
    prompts = OUT / "_shell"
    prompts.mkdir(parents=True, exist_ok=True)
    session_dir = CONFIG / "sessions" / args.arm
    session_dir.mkdir(parents=True, exist_ok=True)
    cmd, env = pi_command(args.arm, session_dir, prompts, args.thinking)
    os.execvpe(cmd[0], cmd + args.rest, env)


def main(argv) -> int:
    p = argparse.ArgumentParser(prog="python -m e09.i3.run")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--questions", help="逗号分隔的问题 id，默认全部")
    r.add_argument("--arms", default=",".join(ARMS))
    r.add_argument("--repeats", type=int, default=1)
    r.add_argument("--thinking", default="high")
    r.add_argument("--label", default="run")
    s = sub.add_parser("shell")
    s.add_argument("arm", choices=ARMS)
    s.add_argument("--thinking", default="high")
    s.add_argument("rest", nargs=argparse.REMAINDER)
    args = p.parse_args(argv)
    return run(args) if args.cmd == "run" else shell(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
