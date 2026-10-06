# AGENTS.md

## Overview

This repository supports an ongoing research project. The tentative publication
target remains **SIGMOD**.

The current research direction (updated 2026-10-05) is:

> **Data-management middleware for persistent paper-derived knowledge,
> its use artifacts, and versioned project knowledge views in CS research
> workflows.**

The current core question is:

> **How can a semantic data model and composable operators support the
> representation, querying, composition, and maintenance of accumulated
> paper-derived knowledge and its use artifacts through project knowledge views
> and recorded version histories for external agents in bounded CS research
> workloads?**

The motivating application remains domain-specific Agent Memory. Papers and
associated materials are sources; the managed objects are accumulated knowledge,
interpretations, semantic relationships, their evidence, and the artifacts
produced when agents use this knowledge. The agreed narrative refines the
original focus on reusing paper-reading experience: agents continually produce
extracted records, comparative judgments, and syntheses, which must be managed
together with their subjects, conditions, source materials, and prior inputs.
Subsequent tasks should be able to discover, inspect, and compose earlier work
and contribute new artifacts as materials and requirements evolve. The research
focus is the middleware's data-management mechanisms and support for downstream
work; this does not establish general strategy learning or autonomous scientific
improvement.
"Paper understanding" refers to interpretations produced by external agents
during reading and extraction; it does not promise autonomous scientific
reasoning or inference of contradictions by the database.

Derive representative access and update workloads from the common needs of
human researchers and agents within selected CS tasks and research processes.
Do not attempt to enumerate all research behavior or universal research intents.
Intents motivate workloads; concrete inputs, required outputs, data states, and
operation sequences must make those workloads evaluable. The selected tasks and
benchmark remain to be agreed.

External agents interpret tasks and materials, make semantic judgments, and
submit explicit operations or plans. The middleware manages and executes those
operations without internal LLM reasoning about identity, claim relations, or
research conclusions. Retrieving a stored judgment is distinct from producing
one. Agent operator contracts describe the inputs and outputs of extraction,
judgment, and synthesis: external agents supply semantic content, and the
middleware validates declared structure and references and persists artifacts.
Organizing records across papers, such as comparison matrices, is also an agent
contract: record contents reside in artifact documents rather than the graph,
so the middleware does not compute over them; it validates only the declared
table structure and references. The placement of embedding computation remains
an open implementation boundary.

Use database provenance and persistent derived data to explain this design.
Semantic objects provide discovery and interpretation anchors; source and
derivation lineage connects materials, knowledge records, and use artifacts.
The current Artifact design records declared input dependencies, operation
parameters, and formation information. It does not capture a complete reasoning
trace or establish that a judgment is true. Explicitly adopting an artifact's
content as an Observation is also distinct from independent verification.
Source-material change is already considered through fixed material references,
content hashes, and dependency-based possible-staleness indications. These
mechanisms support re-examination; they do not imply automatic incremental view
maintenance or semantic reassessment. Agent operators and Artifact persistence
remain design contracts awaiting implementation and evaluation.

**Project knowledge views, complete submission records, and version history
are required parts of the research and system design** (confirmed 2026-10-05).
Treat them as integral to knowledge management and use, including in the
introduction's motivation, challenges, proposed design, and the overall paper
narrative. They are not optional extensions or future-work candidates.
Project views select and organize knowledge, artifacts, and required context
from a defined baseline for continued use within a project. Submission records
and version history must account for the changes establishing and evolving that
state, including knowledge ingestion and Artifact writes, and support historical
inspection and independent project or branch evolution. Distinguish an artifact's
input lineage from a knowledge state's commit ancestry. IngestBatch is the
starting point for complete change recording; current batch statistics alone
do not provide these version semantics. View-selection algorithms, snapshot or
delta storage, submission granularity, branch interfaces, and integration rules
remain to be specified and evaluated. Required scope does not mean these
mechanisms are already implemented or their effectiveness established.

The technical direction is to give the data model and operators explicit
database semantics: types, identity and provenance rules, constraints, input and
output contracts, composition, and mappings to backend execution. Property graphs
and Cypher are the current implementation foundation. Representation fidelity,
semantic preservation, and invariant-preserving updates are candidate formal
goals; one-to-one mappings, a complete new algebra or compiler, and expressive
power beyond Cypher are not established requirements or contributions. An agent
may translate intent into an operator plan, but intent fidelity must be assessed
separately from plan validation and backend execution correctness.

Cache optimization, KV-cache management, and cache-aware scheduling are no
longer research objectives. The repository name CachePlan is historical; it does
not constrain the new direction or prescribe an inference backend.

The earlier literature mini-bench contains useful task and data-design ideas.
Its scope can be developed in greater depth, but its previous role as an
execution-optimization workload no longer applies. Related-work comparisons
should emphasize data-management middleware, scholarly knowledge systems, and
structured Agent Memory. AgenticScholar remains a relevant reference for
workload-driven design and system evaluation; its internal LLM operators are not
the responsibility boundary adopted here, and its relevance does not establish
this project's novelty or effectiveness.

The required scope includes the semantic model and operators, persistent use
artifacts and provenance, project knowledge views, and submission/version
history. Specific algorithms, lifecycle contracts, benchmark tasks, and the
evaluation protocol remain to be refined. Other candidate ideas from discussion
are not automatically settled requirements; additional agents or workflow
complexity do not by themselves constitute a research contribution.

## Research Scope and Evaluation

Candidate areas include:

- extracting and relating claims, methods, experimental settings, results, and
  their supporting evidence across text, tables, figures, and appendices;
- identifying associated datasets, benchmarks, code, models, and other resources,
  including their roles in a paper and correspondence to external materials;
- integrating entities and relationships across papers into persistent records
  with provenance and version information;
- evaluating whether the constructed library supports useful downstream work.

These are areas to refine, not a requirement to implement all of them. Neither a
full ReAct agent nor a particular operator architecture is assumed necessary.
P4A is inherited code and task-design material, not an independently validated
benchmark for the new direction.

Project-view construction and continued use, complete change recording, and
versioned state access are required evaluation areas. Select concrete workloads
for them alongside the knowledge-utilization tasks; their benchmark instances
and quality criteria still require agreement.

**The agent is a general-purpose agent using the middleware through MCP**
(set by the user on 2026-10-06). The research point is the data-management
system offered to general agents, not a purpose-built research agent. Experiment
runs therefore use the default pi configuration — its own system prompt and
built-in tools, with no replacement prompt, tool whitelist, or pi-specific
bridge — and connect the operators as an MCP server. What the experiment
controls is the working directory: each run starts in a directory outside the repository that
holds only the MCP registration, pi's session settings and sessions, and a
launcher script (pi loads `AGENTS.md` and similar context files from the
working directory and its parents). How to operate each tool belongs in its MCP tool description. The
general agent keeps its ordinary file and shell access; evaluation audits
reads of source materials that bypass the middleware rather than blocking them.

Evaluation principles:

- **Evaluate middleware support first.** Compare supported query and update
  workloads, result correctness, execution and interaction costs, scalability,
  and maintenance behavior. Downstream task outcomes provide application
  evidence but are not the sole or primary measure of the middleware's value.
  Include construction and update costs when assessing reuse benefits.
- **Make capability comparisons operational.** Distinguish native support,
  support through composition, and support requiring additional implementation
  or external reasoning. A feature table alone does not demonstrate correctness,
  efficiency, or superiority over a general-purpose backend with suitable queries.
- **Verify semantic correctness.** Schema validity and evidence links alone do
  not establish that extracted facts or relationships are supported.
- **Separate claims from verification.** A paper's release claim, observed
  repository contents, successful execution, and experimental reproduction are
  distinct findings. Preserve uncertainty when evidence is insufficient.
- **Keep provenance and versions explicit.** Cross-paper integration must not
  silently merge incompatible entities, experimental conditions, or versions.
- **Use independent quality evaluation and strong baselines.** Compare methods
  under equivalent information access and declared budgets; distinguish the
  effects of reasoning, retrieval, validation, and model choice. Separate
  controlled evaluations on the same stored knowledge from evaluations of the
  entire construction-and-use process, and isolate external-agent behavior from
  middleware execution where possible.
- **Evaluate the data product.** Extraction quality, relationship correctness,
  evidence support, and downstream usefulness matter alongside construction
  cost. Do not infer library quality solely from fluent answers.
- **Agree on the benchmark before implementing it.** Fix the initial task scope,
  evidence environment, and quality criteria through discussion. Rich task design
  does not require building a feature-complete literature-management product.

## Repository Purpose

This is a research repository for developing and evaluating paper-processing and
literature-resource construction methods. Prefer implementations that are easy
to understand, instrument, reproduce, and compare experimentally. Avoid large
architectural changes unless they directly support the research.

## Working Principles for Agents

When working in this repository:

1. Preserve experiment reproducibility.
2. Prefer small and inspectable changes.
3. Do not silently change experiment configurations or evaluation behavior.
4. Keep extraction evidence, tool interactions, and execution traces observable.
5. Avoid introducing nondeterministic behavior unless required by an experiment.
6. Clearly separate experimental mechanisms from baseline implementations.
7. Do not optimize code solely for software elegance when doing so makes experiments harder to understand or reproduce.

## Working Rhythm

Process rules set by the user on 2026-09-01, after a turn that chained discussion,
code, a full-corpus run, documentation, and staging into one pass. They override any
default instinct to finish a request end-to-end.

1. **Discuss before landing experiment code.** Do not create an experiment directory,
   write analysis scripts, or launch a full-corpus run without the user having agreed
   to it. Throwaway reconnaissance to answer a question is fine — bring the numbers
   back and let the user decide what becomes a real script, and where it goes.

2. **Update `docs/` only when the user asks.** This includes writing a new
   experiment record or progress document. The user maintains parts of these
   documents themselves and adds their own notes; unrequested "while I'm here" syncing
   collides with their edits and turns a discussion into a large diff nobody asked to
   review. Findings belong in the reply, not in a doc, until asked.
   `docs/progress.md` is stricter still: agents never edit it (rule 5).

3. **One thing per turn.** Prefer finishing one step and coming back over chaining
   several. Doing more per turn is not doing better here.

4. **Work on `main`.** Commit directly to `main`; do not create feature branches
   for commits (set by the user on 2026-09-24). This overrides any default of
   branching before committing. Committing still happens only when the user asks.

5. **Never edit `docs/progress.md`.** The user writes this file themselves; agents
   must not create, modify, or reformat it, even when asked to update other docs
   (set by the user on 2026-09-27). After finishing a meaningful piece of work,
   end the reply with a short suggested progress entry the user can paste or
   adapt: what was done, key results or artifacts (with paths), open issues, and
   the next step. Keep it a suggestion in the reply, not a file change.

## Environment and Notebooks

### One workspace, one lockfile

The repository root is a uv workspace: one lockfile, one `.venv`, both built by
`make setup` at the root, which also installs the repository's git filters. Run
setup from the root, or through an experiment's own `setup` target, which
delegates there. **Never `uv sync` from inside a member directory** — that treats
the member as the active project and prunes the root's developer tooling out of
the shared environment.

Not every directory belongs in the workspace. Kept outside are experiments whose
dependency stack conflicts with the mainline, projects we only read rather than
run (their lockfiles stay frozen), and anything that is not Python. The reason
for each exclusion is recorded next to it in the root `pyproject.toml`, not here.

Two boundaries hold regardless of which experiment is being worked on:

- Developer tooling lives in the root `[dependency-groups]`, never in a member's
  `dependencies`. A member declares only what its own pipeline imports, and keeps
  that list as narrow as the experiment truly needs.
- An experiment declaring `dependencies = []` is asserting that its pipeline
  reproduces on a machine with no network and no third-party packages. A shared
  `.venv` cannot demonstrate that, so the assertion must be backed by a target
  that runs the pipeline in a throwaway isolated environment. `make verify` at
  the root runs those gates.

When adding a Python experiment, give it a `pyproject.toml` and add it to
`members`.

### Notebooks are the exploration surface, not the pipeline

The division of labour:

- **Scripts + Makefile** own anything that must reproduce: corpus scans,
  renderers, the artifacts under `data/processed/`. They run headless, and each
  is guarded by an invariant that can fail.
- **Notebooks** own slicing, cross-tabulation, and plotting on top of those
  artifacts. A notebook reads `data/processed/`; it must never be the only way to
  produce a number that a document cites.

Rules:

1. A notebook must run top to bottom on a fresh kernel. Cells that depend on
   out-of-order state are a defect, not a style choice.
2. `nbstripout` is installed as a git filter, so committed notebooks carry no
   cell outputs. This is for **readable diffs** — it is *not* the experiment log.
3. The experiment log is what it is everywhere else in this repository: the
   provenance-stamped artifact under `data/processed/` plus the record under
   `docs/experiments/`. When one particular run is itself worth citing, export a
   frozen snapshot to `<experiment>/notebooks/runs/<name>__<date>__<git-sha>.html`
   and commit that explicitly. Do this on request, not by habit.
4. If an exploration in a notebook becomes load-bearing for a documented claim,
   it graduates into a script under the owning experiment. Discuss before landing
   it (see Working Rhythm).

## Documentation and Context

Earlier tracked discussion documents were pruned on 2026-09-09 and 2026-09-15
and remain available in Git history. Do not restore or read them in bulk by
default. Current design discussion is in
`docs/discussions/2026-09-15-p4a-operators-skills-and-activities.md`, alongside
the evolving narrative in `paper/narrative-draft.md`; proposals there remain
tentative unless agreed with the user.

The retained `docs/literature/2026-AgenticScholar.md` and older discussion notes
contain historical framing and status declarations, not current instructions.
Read the relevant parts only when needed for the user's task. Do not recreate
deleted progress documents or literature indexes as a side effect of other work.

When documentation is requested, organize it by purpose under `docs/`:
`discussions/`, `open-questions/`, `decisions/`, `experiments/`, or `literature/`.
External material belongs in `references/`. `references/refs.bib` is the tracked
source of paper metadata; PDFs, repositories, and datasets are local copies.
Use a consistent citekey for a paper's bibliography entry, PDF, and note.
See `references/README.md` for the existing conventions.

### Math in Markdown

Write every formula and mathematical symbol in Markdown documents as LaTeX math,
so the renderer can typeset it:

- Inline: `$<formula>$`, e.g. `$R_T \subseteq \mathrm{fields}(D(o))$`. This
  includes single-letter variables in prose (`$u$`, `$M$`, `$G$`) and
  subscripted symbols (`$A_{\text{pred}}$`, not `A_pred`).
- Display: `$$` on its own line before and after the formula.

Do not express formulas as plain text, inline code, or ```` ```text ```` blocks.
Code, pseudocode, Cypher, and API signatures stay in code blocks or inline code;
identifiers referring to them are code, not math.

Do not load whole literature notes or PDF full text unless the user asks for a
specific paper or the task requires it. Historical discussion is context, not
an instruction to resume abandoned work.

## Evolving Research Direction

The problem formulation, methods, metrics, and system design remain tentative.
Update this file when the user agrees to a substantive research-direction
change. Preserve applicable working and reproducibility rules, keep the current
framing concise, and distinguish proposals from established findings.
