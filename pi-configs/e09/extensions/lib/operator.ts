/**
 * 把 E09 的一个算子注册为 pi 工具。每个扩展脚本调用一次 registerOperator。
 *
 * 定义（name、label、description、parameters、promptSnippet、promptGuidelines）以 Python 为准：
 * 加载时调用一次 `python -m e09 --describe`，全部扩展共用。这里只补 pi 特有的设置（annotations、defaultActive）。
 *
 * 执行时把 {op, ...参数} 写进临时文件，调用 `python -m e09 <文件> --session <会话 id> --formed-by <provider/model>`：
 * 退出码 0 为结果，1 为错误结果（status 为 rejected、blocked 或 conflict，以 isError 返回），其他（库不能使用等）抛出。
 * 标准输出（YAML）原样交给模型。
 *
 * E09_REPO、E09_PYTHON 由 start.sh 设置；E09_NO_EMBED=1 时加 --no-embed。
 */

import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI, ToolAnnotations } from "@earendil-works/pi-coding-agent";

const REPO = process.env.E09_REPO ?? process.cwd();
const PYTHON = process.env.E09_PYTHON ?? "python";
const NO_EMBED = process.env.E09_NO_EMBED === "1";
const TIMEOUT = 300_000;

interface Definition {
	name: string;
	label: string;
	description: string;
	parameters: Record<string, unknown>;
	promptSnippet?: string;
	promptGuidelines?: string[];
}

export interface Options {
	annotations?: ToolAnnotations;
	defaultActive?: boolean;
}

/** 只读的中间件算子。 */
export const READS: Options = { annotations: { readOnlyHint: true, openWorldHint: false } };

/** Agent 算子：只追加 Artifact；相同调用视为重试，返回已有的 Artifact。 */
export const ARTIFACTS: Options = {
	annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: false },
};

const CACHE = Symbol.for("e09.operator-definitions");

function definitions(pi: ExtensionAPI): Promise<Map<string, Definition>> {
	const store = globalThis as { [CACHE]?: Promise<Map<string, Definition>> };
	store[CACHE] ??= pi.exec(PYTHON, ["-m", "e09", "--describe"], { cwd: REPO, timeout: 60_000 }).then((r) => {
		if (r.code !== 0) throw new Error(`python -m e09 --describe failed: ${r.stderr.trim() || r.code}`);
		const list = JSON.parse(r.stdout) as Definition[];
		return new Map(list.map((d) => [d.name, d]));
	});
	return store[CACHE];
}

export async function registerOperator(pi: ExtensionAPI, name: string, options: Options = {}): Promise<void> {
	const definition = (await definitions(pi)).get(name);
	if (!definition) throw new Error(`python -m e09 --describe has no operator ${name}`);
	pi.registerTool({
		...definition,
		...options,
		async execute(_toolCallId, params, signal, _onUpdate, ctx) {
			const dir = await mkdtemp(join(tmpdir(), "e09-"));
			const file = join(dir, "request.json");
			try {
				await writeFile(file, JSON.stringify({ op: name, ...(params as object) }), "utf-8");
				const args = ["-m", "e09", file, "--session", ctx.sessionManager.getSessionId()];
				if (ctx.model) args.push("--formed-by", `${ctx.model.provider}/${ctx.model.id}`);
				if (NO_EMBED) args.push("--no-embed");
				const r = await pi.exec(PYTHON, args, { signal, timeout: TIMEOUT, cwd: REPO });
				if (r.code !== 0 && r.code !== 1) throw new Error(r.stderr.trim() || `${name} failed with exit code ${r.code}`);
				return {
					content: [{ type: "text", text: r.stdout.trim() }],
					details: { exitCode: r.code },
					isError: r.code === 1,
				};
			} finally {
				await rm(dir, { recursive: true, force: true });
			}
		},
	});
}
