# Graph schema (Neo4j)

The store also holds unrelated objects from other domains; restrict queries accordingly.

Node labels (every semantic object has two labels: a family and a kind):

| Labels | Properties |
| --- | --- |
| `Entity:Paper` | `id`, `name` (title), `identifiers` (list, e.g. `arxiv:2205.13504`), `description`, `stub`, `note` |
| `Entity:Dataset` | `id`, `name`, `identifiers`, `description`, `note` |
| `Concept:Method`, `Concept:Metric`, `Concept:Task` | `id`, `name`, `definition`, `note`; Method also `stub`; Metric also `direction` |
| `Content:Experiment` | `id`, `exp_key`, `anchor`, `section`, `lines` ([start, end]), `text`, `setting`, `note`, `cond_split`, `condition_basis` |
| `NameKey` | `raw` (a name or alias as written), `key`, `kind`, `scope`, `status` |
| `Material` | `id`, `path`, `content_hash` |

Names and aliases are not lists on objects: every name or alias is a `NameKey` node linked by `(:NameKey)-[:NAMES]->(object)`; `raw` keeps the spelling and case.

Relationships:

| Pattern | Properties |
| --- | --- |
| `(:Experiment)-[:EVALUATES]->(:Method)` | `role` (target / baseline), `variants` (list), `origin` (own / rerun / cited / unstated), `origin_basis` (locator), `origin_from` (paper id) |
| `(:Experiment)-[:USES]->(:Dataset)` | `role` (evaluation_data) |
| `(:Experiment)-[:MEASURED_BY]->(:Metric)` | |
| `(:Experiment)-[:ON_TASK]->(:Task)` | |
| `(:Experiment)-[:FROM]->(:Paper)` | `material_ref` (Material id), `locators` (list of `<section>::<start>:<end>`) |
| `(:Paper)-[:CITES]->(:Paper)` | `source_refs` (list), `description` |
| `(:Dataset)-[:PART_OF]->(:Dataset)` | |
| `(:Material)-[:MATERIAL_OF]->(:Paper)` | |

Two generic examples:

```cypher
// find objects by a name or alias, case-insensitively
MATCH (k:NameKey)-[:NAMES]->(o) WHERE toLower(k.raw) = toLower($name)
RETURN o.id, labels(o), k.raw
```

```cypher
// the experiments of one paper with their tables and source locators
MATCH (e:Experiment)-[f:FROM]->(p:Paper {id: $paper})
RETURN e.exp_key, e.text, f.material_ref, f.locators ORDER BY e.exp_key
```
