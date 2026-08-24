# LVL-09 adaptive playout lead setup plan

**Goal:** make the manual latency harness capable of a clean later A1=1000/B=250/A2=1000 screen without changing product behaviour.

**Risk:** Tier 2 operational state/cancel fence. **Dependencies:** clean committed source, repaired driver Gate. **Exclusions:** Chrome/Provider/product default.

1. Add deterministic private-harness tests for manifest arm order, completed/matching advance, retained failed/mismatched rows, authoritative snapshot naming and process-group escalation.
2. Repair private `lv-driver.sh`: validate a LVL-09 manifest before launch; derive expected profile/case/round; only beep/advance on matching completed export; snapshot all rows using row identity; start services with `setsid`; drain/terminate/kill whole groups.
3. Add a small tracked JSON validator/reducer only if the existing probe validator cannot validate the LVL-09 arm manifest. Its tests must reject malformed arms, non-A1/B/A2 order and changed source/configuration.
4. Run harness tests, any validator tests, affected frontend tests only if frontend source changes, `git diff --check`, then independently review Tier-2 driver diff.
5. Commit only tracked spec/plan/validator changes. Private harness and driver remain outside Git; return exact hashes and operator commands. Physical A1/B/A2 remains a separate human step.
