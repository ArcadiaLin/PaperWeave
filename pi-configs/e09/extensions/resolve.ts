/** Resolve：把提及、标识符或描述解析为库中的 Entity 或 Concept。 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { READS, registerOperator } from "./lib/operator.ts";

export default (pi: ExtensionAPI) => registerOperator(pi, "Resolve", READS);
