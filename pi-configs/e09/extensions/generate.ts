/** Generate：按用途生成的文本（报告、方案等），写成 Artifact。 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { ARTIFACTS, registerOperator } from "./lib/operator.ts";

export default (pi: ExtensionAPI) => registerOperator(pi, "Generate", ARTIFACTS);
