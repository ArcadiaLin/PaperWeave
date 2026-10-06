/** Verify：判断一条主张在给定依据下是否成立，写成 Artifact。 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { ARTIFACTS, registerOperator } from "./lib/operator.ts";

export default (pi: ExtensionAPI) => registerOperator(pi, "Verify", ARTIFACTS);
