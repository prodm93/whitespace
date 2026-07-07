# WhiteSpace

*Find your whitespace.*

An adversarial multi-model patent analysis and ideation engine. Given a technical domain and your professional profile, it builds a knowledge graph from patents, web sources and your own documents, surfaces unmet needs in the patent landscape that match your expertise, and develops the ones you pick into fleshed-out, prior-art-checked invention proposals.

## Status

**v0.1 (current): scaffolding.** Infrastructure, CI/CD, deployment (AWS SaaS + local BYOK Docker), tri-modal search pipeline and knowledge graph construction are in place. The adversarial council architecture is landing on the `autonomous-agentic-architecture-migration` branch.

Two things to know while reading the code at this stage:

- Model-to-role assignments in `model_registry.yaml` are temporary defaults, not the final allocation. The real allocation (critics never share a provider with the agents they judge, tiered model selection per council) lands as a dedicated commit.
- This README is itself a WIP stub. Full documentation ships with v0.2 once the end-to-end pipeline runs.
