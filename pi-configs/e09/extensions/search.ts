/** Search：按查询与结构条件找某一类对象，返回读视图。 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { READS, registerOperator } from "./lib/operator.ts";

export default (pi: ExtensionAPI) => registerOperator(pi, "Search", READS);
