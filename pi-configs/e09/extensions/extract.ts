/** Extract：把读到的具体信息取成结构化记录，写成 Artifact。 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { ARTIFACTS, registerOperator } from "./lib/operator.ts";

export default (pi: ExtensionAPI) => registerOperator(pi, "Extract", ARTIFACTS);
