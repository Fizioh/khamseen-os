# Skills Registry and Capability Routing Contract

This contract defines how domain modules declare **capabilities**, **skills**, and **tools**, and how work routes to scoped agent runs without coupling to vendor-specific skill formats.

## Vocabulary

| Primitive | Format | Purpose |
|-----------|--------|---------|
| **Capability** | `<domain>.<action>` (e.g. `code.write`, `review.independent`, `literature.synthesize`) | Routing label declaring what class of work a role or skill can accept. |
| **Skill** | `SkillSpec(id, capabilities, allowed_tools, requires_human_approval)` | Packaged behavior binding capabilities to an explicit allowlist of tools and approval policy. |
| **Tool** | `<namespace>.<action>` (e.g. `git.diff`, `pytest.execute`, `corpus.search`) | Executable action registered in the module's tool catalog. |

## Routing flow

1. **Incoming `Task`**: Declares `domain`, `allowed_tools`, `allowed_scopes`, and optional `sensitive_actions`.
2. **Capability match**: The module selects a skill whose `capabilities` match the requested stage (`IMPLEMENT` vs `REVIEW`).
3. **Allowlist intersection**: `ExecutionRequest.allowed_tools` is restricted to the skill's `allowed_tools`, which must be a subset of the module's declared `tools`.
4. **Pre-run policy evaluation**: `PolicyEngine.evaluate_pre_run` rejects any `Run` requesting tools outside `Task.allowed_tools` or scopes outside `Task.allowed_scopes`.

## Domain examples (synthetic)

### 1. Engineering module (`examples/engineering-loop/module-manifest.json`)

- **Chief role**: `engineering_chief`
- **Capabilities**: `code.write`, `tests.verify`, `review.independent`, `release.publish`
- **Skills**:
  - `bounded_patch_implementer` → tools: `git.diff`, `git.commit`, `pytest.execute`, `ruff.check`
  - `independent_pr_reviewer` → tools: `git.diff`, `pytest.execute`, `ruff.check` (no `git.commit` write tool)
  - `release_publisher` → tools: `git.diff`, `github.pr.create` (`requires_human_approval: true`)

### 2. Research module (illustrative)

```json
{
  "id": "research",
  "version": "0.1.0",
  "chief_role": "research_chief",
  "capabilities": [
    "literature.search",
    "evidence.synthesize",
    "review.methodology"
  ],
  "tools": [
    "corpus.query",
    "citation.verify",
    "report.render"
  ],
  "data_scopes": [
    "corpus:public_papers",
    "notes:workspace"
  ],
  "approval_policy": "policies/research-default.json",
  "skills": [
    {
      "id": "literature_synthesizer",
      "capabilities": ["literature.search", "evidence.synthesize"],
      "allowed_tools": ["corpus.query", "citation.verify", "report.render"],
      "requires_human_approval": false
    },
    {
      "id": "methodology_reviewer",
      "capabilities": ["review.methodology"],
      "allowed_tools": ["corpus.query", "citation.verify"],
      "requires_human_approval": false
    }
  ]
}
```

## Non-goals

- Khamseen OS does not mandate a proprietary prompt template engine or vendor-specific skill bundle format.
- Native runtime skills (such as Hermes Agent `--skills`) are invoked through adapter parameters after passing module manifest and policy validation.
