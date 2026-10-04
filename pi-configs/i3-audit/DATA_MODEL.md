# The store

Both papers have been read and recorded in a graph store at report level: every results table of each paper is one stored experiment. The store records what each table compares, on which datasets and metrics, under which conditions, and where the table is in the paper. **Numbers are not stored**: read the table itself to get values.

Objects (each has an `id` such as `method_0036`, and a `name`):

- **Paper**: the two papers, plus placeholder papers (`stub: true`) for cited papers that have not been read; placeholders carry only the title as printed in a bibliography.
- **Method**: methods compared in the tables. A paper's own method has a definition; baselines are placeholders (`stub: true`) with a name only. Variants (e.g. PatchTST/42, DLinear-S) are not separate objects; they appear as printed labels on the experiment.
- **Dataset** (with parts: ETTh1, ETTh2, ETTm1 and ETTm2 are parts of ETT), **Metric** (with `direction`, e.g. lower is better), **Task**.

Each **experiment** (one results table) has:

- `exp_key` = `<paper id>::<anchor>`. The anchor names the table: `S4.T3` is Table 3 (in Section 4), `A1.T15` is Table 15 (in the appendix).
- `text` (what the table measures), `setting` (conditions in prose: look-back window L, horizons T, training, legend of variant labels), `note` (doubts recorded when the table was read, e.g. suspected misprints), `cond_split` (the split convention the paper declares, with its basis).
- The participating methods, each with: `role` (target or baseline), `variants` (labels exactly as printed in the table), `origin` — how the paper says it obtained the numbers: `own` (the paper's own method), `rerun` (the authors ran the baseline), `cited` (copied from another paper; `origin_from` is that paper's id) or `unstated` (the paper does not say) — and `origin_basis`, the location of the sentence that states it.
- The datasets and metrics of the table, and the source locator of the table.

`origin` only records what the paper states; equal numbers alone do not show that results were copied. A paper may cite results from another paper; the citation is recorded as a `CITES` link between the two papers with a short description.

**Locators.** Text is located by line numbers in the paper's stored Markdown. A full source reference is `<material_id>::<section>::<start>:<end>`; a locator inside the same paper is written `<section>::<start>:<end>`.
