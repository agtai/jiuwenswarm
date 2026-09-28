# Launch plan: Blackboard beta

## Summary

Blackboard lets people and agents co-write documents. The beta opens to **three teams** on October 6.

## Timeline

| Week | Milestone | Owner | Status |
| --- | --- | --- | --- |
| 39 | Feature freeze | Alice | done |
| 40 | Beta invites | Bob | in progress |
| 41 | Feedback review | Chen | planned |

## Risks

- **Host reachability.** Members behind NAT cannot reach a laptop host.
  - Mitigation: run the host on the team server.
- **Markdown fidelity.** Tables with several blocks per cell do not survive.
- **Load.** Unknown beyond 20 open documents.

## Checklist

- [x] Security review
- [ ] Load test report
- [ ] Docs site update

---

Questions go to the #blackboard channel.
