/** MatrixConstruct：Agent 填写的行 × 列矩阵，中间件只校验表格结构，写成 Artifact。 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { ARTIFACTS, registerOperator } from "./lib/operator.ts";

export default (pi: ExtensionAPI) => registerOperator(pi, "MatrixConstruct", ARTIFACTS);
