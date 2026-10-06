/** Traverse：从已确认的对象出发，沿声明的关系逐跳走并保留路径。 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { READS, registerOperator } from "./lib/operator.ts";

export default (pi: ExtensionAPI) => registerOperator(pi, "Traverse", READS);
