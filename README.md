# FlowPilot

FlowPilot is an AI financial-optimization copilot built on BMONI. It helps users organize money into smart pockets, detect financial risks and opportunities, and execute transparent, user-approved actions.

## Monorepo structure

```text
flow-pilot/
├── backend/    FastAPI service, tests, and BMONI boundary
├── frontend/   Flutter application workspace
└── docs/       Shared product, architecture, security, execution, and pitch material
```

## Start here

- [Product requirements](docs/PRD.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API contract](docs/API.md)
- [Security baseline](docs/SECURITY.md)
- [Tonight's runbook](docs/TONIGHT_RUNBOOK.md)
- [Presentation pitch](docs/PRESENTATION_PITCH.md)
- [Backend setup](backend/README.md)
- [Frontend workspace](frontend/README.md)

## Work allocation

- Favour owns the heavy platform/security/BMONI integration work in [GitHub issue #1](https://github.com/baalebos-cloud/flow-pilot/issues/1).
- The second backend developer owns pockets, insights, fixtures, and frontend-facing contracts in [GitHub issue #2](https://github.com/baalebos-cloud/flow-pilot/issues/2).

