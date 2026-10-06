/** ReadEvidence：读来源引用所指的论文材料或 Artifact 文档中的行。 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { READS, registerOperator } from "./lib/operator.ts";

export default (pi: ExtensionAPI) => registerOperator(pi, "ReadEvidence", READS);
