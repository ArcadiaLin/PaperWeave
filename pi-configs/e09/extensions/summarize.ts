/** Summarize：带引用的总结，写成 Artifact。 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { ARTIFACTS, registerOperator } from "./lib/operator.ts";

export default (pi: ExtensionAPI) => registerOperator(pi, "Summarize", ARTIFACTS);
