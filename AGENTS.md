# Exploratory shared-flash research — provisional

## Intent and authorization

This is early exploration, not implementation of a final LEDGER specification.
The question is whether logical write bytes adequately represent physical NAND
work/wear for services and LLMs on shared edge storage. Problem statement,
contributions, accounting, placement, architecture, KV policy and even LEDGER may
change with evidence. Measurement validity comes before preserving an idea.

- Current authorization is a small initial-history control only: same 4 GiB raw / 3 GiB exposed,
  approximately 70% live logical fill; only random preconditioning changes from one to three identical passes,
  GC/erase gate, 4 KiB sequential versus uniform random overwrites, direct I/O,
  QD1/job1/equal byte budgets. Reuse the archived one-pass seed 42 baseline; run two new three-pass runs, one per pattern. Commit/push remains authorized.
- Do NOT run other E0 workloads, fill/OP/GC/geometry sweeps,
  extra repetitions beyond the approved three per pattern, LLM downloads,
  accounting/Shapley/BPF, SAVE/DROP policies,
  threshold/paced, placement features or real-device experiments in this phase.
- An unsuitable host is a recorded blocker. Do not install/run FEMU under WSL or
  substitute TCG/nested VM results for supported physical Linux/KVM measurements.
- Do not reboot, repartition, install an OS or access an unspecified remote host.
- The authorized lab server is shared. ALL remote file creation/modification must
  stay inside the user's ledger directory. Never change system packages, service
  configuration, groups, permissions outside that directory, or other users'
  work. No sudo/apt/usermod/host upgrade. Python venv, caches, build trees and
  guest images belong inside ledger. Read-only host inspection is allowed.
- Start each SSH check without multiplexing (ControlMaster=no, ControlPath=none,
  ControlPersist=no). The user has separately arranged KVM group access; verify
  the execution session's groups, R/W, open and API before using it.
- Build uses at most 2 jobs, nice 10 and 2-CPU affinity. Keep one VM, guest
  2 GiB/2 vCPUs, 4 GiB raw/3 GiB exposed, nice 10, at most 6-CPU affinity and
  12 GiB process address-space limit. All caches/TMPDIR/HOME for build tools
  are project-local. Stop the owned VM after each run; never stop other users' jobs.
- Stop after the initial-history control and design of the unexecuted three-pattern experiment for the user's decision. A blocked runtime stays incomplete;
  source/docs preparation is not successful build, boot or sanity.

- The six original Phase 2 pilot runs are COMPLETE and must be preserved.
  The six longer same-profile overwrite runs are also COMPLETE. Do not rerun or extend them.
  The newer user instruction authorizes the small three-pass history control only.
  Use fixed byte windows and frozen convergence/comparison criteria. Sequential/permutation/
  replacement comparison is DESIGN ONLY; no other workloads, sweeps or phase transitions are authorized.

## Documents and evidence

- Preserve docs/LEDGER*.html byte for byte. These are historical source records.
- Reference priority: report (2026-10-06), proposal (2026-09-28), summary (2026-09-22).
  They are not final specifications. The user's latest instruction takes priority.
- Record conflicts in docs/DOCUMENT_CONFLICTS.md. Training and inference are
  historical candidate directions, not a predetermined winner.
- Supplied results are reported claims until reproduced. No ftlsim source/raw
  traces/analysis scripts are currently supplied.
- Keep all research directions provisional; retain negative results and rejected
  or superseded decisions. Record more interesting observations as candidate questions.
- Phase 5 selects a solution using evidence. Threshold/paced are not mandatory.

## Measurement rules

- Distinguish application bytes, NVMe logical bytes, modeled physical writes,
  modeled erases, derived metrics and real hardware evidence.
- FEMU is an NVMe emulator, not a Raspberry Pi eMMC/SD replica.
- Pin external/FEMU to external/femu.lock.json; check source/schema at that commit.
- Prefer native counters. Instrument only a demonstrated missing metric.
- At the pinned commit NAND user programs exclude GC copies. Physical programs
  are their sum; window WAF uses deltas, not subtraction of cumulative ratios.
- Reset baseline is a fresh QEMU process and deterministic reconstruction.
  Guest reboot, controller reset, TRIM, format and boot-disk snapshots differ.
- No GC, inadequate warmup, invalid reset, mismatched bytes or wide uncertainty
  cannot disprove a mechanism. Phase 1 sanity is not a research result.
- Null means unavailable/unmeasured, never zero. Never label examples as measured.

## Reproducibility and sharing

- Git: source/config/scripts/small JSON/CSV. Exclude checkouts, VM/model/trace
  binaries, credentials and private host connection details.
- Record project commit/dirty state, FEMU commit, config/workload hash, host and
  guest info, seeds, timestamps, artifact locations and status.
- Same config may run at home or a lab. Record host differences and compare within
  controlled hosts; never merge their performance figures as interchangeable runs.
- Use stdlib Python tools; offline validation is not FEMU runtime validation.

## HTML notes

- Write Korean for students: define terms, give examples, explain why.
- New docs/index.html, research-map.html, phase-XX.html, experiment-log.html,
  decision-log.html and glossary.html contain inline CSS and local navigation,
  with no CDN/runtime network dependency. Use emoji only for status markers.
- Separate observations, interpretations, plans and uncertainties.
- JSON/CSV/logs are source of truth; HTML is the explanation layer. Update records/
  then tools/render_docs.py; do not hand-edit generated numeric results.
- Every future phase adds an HTML note. Preserve source-document hashes and run
  meaningful validation. Do not claim a runtime check without an actual run.
