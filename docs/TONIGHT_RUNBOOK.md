# Tonight's build runbook

## Definition of done

- A new user can register and receive an internal-to-BMONI mapping in mock mode.
- The app can link an SDK-generated public address.
- A user can create protected and discretionary pockets.
- Currency Shield can reject unsafe recommendations and create a safe one from fixture data.
- Approval is idempotent and produces a traceable mock conversion.
- The full path is tested and demonstrable through Swagger.
- Real BMONI unknowns are documented, not guessed.

## Order of execution

1. Agree on fixture: CNGN 300,000 balance; pockets; CNGN 40,000 shield suggestion; USD target.
2. From `backend/`, run backend tests and launch Swagger in mock mode.
3. Frontend builds against the published API examples.
4. Obtain and document BMONI sandbox contract.
5. Replace mock adapter methods one at a time and add contract tests.
6. Prove one real quote/conversion path before UI polish.
7. Run security checks, rehearse live and simulated paths, freeze demo data.

## Demo fallback

Mock mode must show a visible `SIMULATED SANDBOX FLOW` label. Never imply that a synthetic rate, investment opportunity, or completed conversion is live.
