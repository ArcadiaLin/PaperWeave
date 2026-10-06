/**
 * Commit：提交一份 graph-doc，改动库中的知识对象与关系（dry_run 返回 graph-plan，apply 后返回 graph-result）。
 * 默认注册但不启用；E09_ENABLE_COMMIT=1 时启用。
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { registerOperator } from "./lib/operator.ts";

export default (pi: ExtensionAPI) =>
	registerOperator(pi, "Commit", {
		annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: false },
		defaultActive: process.env.E09_ENABLE_COMMIT === "1",
	});
