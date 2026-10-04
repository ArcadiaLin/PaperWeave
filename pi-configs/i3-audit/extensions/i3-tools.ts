/**
 * I3 实例的工具：按组别（环境变量 I3_ARM）注册，每次调用经 pi.exec 交给 Python 的 e09.tools 执行。
 *
 *   S         resolve、experiments、get、read_evidence（中间件算子）
 *   S-Cypher  cypher（只读事务）、read_evidence
 *   R0        不注册工具：两篇论文全文在 system prompt 中
 *
 * I3_PYTHON 是仓库 .venv 的 python，I3_REPO 是仓库根；都由 e09.i3.run 设置。
 * 工具说明三组共用同一份措辞（read_evidence 对 S 与 S-Cypher 完全相同）。
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const ARM = process.env.I3_ARM ?? "";
const PYTHON = process.env.I3_PYTHON ?? "python";
const REPO = process.env.I3_REPO ?? process.cwd();

const KIND = Type.String({ description: "Kind of the object: Method, Dataset, Metric, Task or Paper" });

const TOOLS = {
	resolve: {
		label: "Resolve",
		description:
			"Resolve a name (as printed in a paper) to the id of a stored object of the given kind. Exact name or alias " +
			"matches return status=resolved with one ref; otherwise status=candidates lists similar objects (not confirmed: " +
			"decide yourself whether one is the same object). Pass identifier (e.g. arxiv:2205.13504) for papers if known.",
		parameters: Type.Object({
			mention: Type.Optional(Type.String({ description: "Name as printed, e.g. 'DLinear', 'ETTh1', 'MSE'" })),
			identifier: Type.Optional(Type.String({ description: "<namespace>:<value>, e.g. arxiv:2211.14730" })),
			kind: KIND,
		}),
	},
	experiments: {
		label: "Experiments",
		description:
			"List stored experiments (one per results table) that evaluate any of the given methods. Optional filters: dataset " +
			"(exact by default; include ['parts'] to also match sub-datasets such as ETTh1 under ETT), metric, and scope " +
			"(list of paper ids). Each item gives the table anchor, text, setting, note, conditions, all participants with " +
			"role, printed variant labels, origin (own / rerun / cited / unstated), origin_basis (locator in the same paper) " +
			"and origin_from (cited paper id), datasets, metrics, and source locators. Numbers are not stored: read the " +
			"table with read_evidence. Arguments take ids from resolve, not names.",
		parameters: Type.Object({
			subjects: Type.Array(Type.String(), { description: "Method ids, e.g. ['method_0036']" }),
			dataset: Type.Optional(
				Type.Object({
					ref: Type.String({ description: "Dataset id" }),
					include: Type.Optional(Type.Array(Type.String(), { description: "['parts'] and/or ['versions']" })),
					depth: Type.Optional(Type.Number({ description: "Expansion depth, 1-3 (default 1)" })),
				}),
			),
			metric: Type.Optional(Type.String({ description: "Metric id" })),
			scope: Type.Optional(Type.Array(Type.String(), { description: "Paper ids; omit for all papers" })),
			budget: Type.Optional(Type.Number({ description: "Max experiments returned (default 50)" })),
			continuation: Type.Optional(Type.Number({ description: "Offset from a previous truncated call" })),
		}),
	},
	get: {
		label: "Get",
		description: "Get stored objects by id: kind, name, aliases, identifiers and properties (definition, note, stub flag).",
		parameters: Type.Object({ refs: Type.Array(Type.String(), { description: "Object ids" }) }),
	},
	read_evidence: {
		label: "Read evidence",
		description:
			"Read lines of a paper's stored text. A source_ref is '<material_id>::<section>::<start>:<end>' (1-based, " +
			"inclusive line numbers). Experiments carry such refs; a locator '<section>::<start>:<end>' found elsewhere " +
			"(e.g. origin_basis) is read by prefixing the material_id of the same paper. Tables are Markdown.",
		parameters: Type.Object({ source_refs: Type.Array(Type.String()) }),
	},
	cypher: {
		label: "Cypher",
		description:
			"Run a read-only Cypher query against the Neo4j store (writes are rejected). Returns up to 200 rows; nodes are " +
			"returned with their labels and properties. Use $parameters for values.",
		parameters: Type.Object({
			query: Type.String(),
			params: Type.Optional(Type.Record(Type.String(), Type.Any())),
		}),
	},
} as const;

const ARMS: Record<string, (keyof typeof TOOLS)[]> = {
	S: ["resolve", "experiments", "get", "read_evidence"],
	"S-Cypher": ["cypher", "read_evidence"],
	R0: [],
};

export default function (pi: ExtensionAPI) {
	const names = ARMS[ARM];
	if (!names) throw new Error(`I3_ARM must be one of ${Object.keys(ARMS).join(", ")}; got '${ARM}'`);
	for (const name of names) {
		const spec = TOOLS[name];
		pi.registerTool({
			name,
			label: spec.label,
			description: spec.description,
			parameters: spec.parameters,
			async execute(_toolCallId, params, signal) {
				const r = await pi.exec(PYTHON, ["-m", "e09.tools", name, JSON.stringify(params)], {
					signal,
					timeout: 120_000,
					cwd: REPO,
				});
				if (r.code !== 0) throw new Error(r.stderr.trim() || `${name} failed with exit code ${r.code}`);
				return { content: [{ type: "text", text: r.stdout.trim() }], details: {} };
			},
		});
	}
}
