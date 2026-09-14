# Release 1: qualified reference autonomy

Release 1 is complete. Open [the illustrated report](report.html),
[executed validation](validation.json) and [the guided investigation](demo.md).
The report includes the updated Releases 2 and 3 roadmap. Neither later release
has been started by this increment.

[Publication checks](publication-check.json) cover every case selector, keyboard
playhead control, narrow screens, local links and twenty saved Model outputs with
the network disabled. Desktop and mobile captures were reviewed visually. These
checks concern the report; they are separate from the application browser suite.

The frozen programme contains all 59 prior version-4 cases, plus 27 common-local
and 18 common-joint controller executions (three event seeds and three numerical
repetitions): 104 completed cases and 8,352 hourly intervals. Original editions are
retained. Forty cases were originally restored but unconfirmed: eighteen now confirm,
twenty remain unconfirmed and two finish impaired. Numerical correctness does not
mean successful recovery. All outcomes remain in the report.

The final application content identity is
`a81a0aec58f143583ac800b8d7c2b0fbb591bea93739dad0f3d21dc9d806737d`.
The frozen numerical programme uses
`55aa6d80fd4462f04cb5095cdff6a9ae28bc15fb67c074f7d980592a749c3b44`.
[The dated review](frozen-source-review.json) records the exact differences and
preserves the original stale assumption-review status. Final documentation is fresh;
the numerical study is not relabelled as a final-source execution.

Run the saved programme with:

```
.venv/bin/python -m methane.release_qualification run research/release-1/3a3e10655452448a91ab784fb43cc0bd
.venv/bin/python -m methane.release_qualification report research/release-1/3a3e10655452448a91ab784fb43cc0bd
```

The saved raw report is
`3a3e10655452448a91ab784fb43cc0bd/reports/f8cb91d20eff4b298acf67bacb19b704/results.json`.
To generate a new readable edition from those original operands:

```
.venv/bin/python research/release-1/writeup.py research/release-1/3a3e10655452448a91ab784fb43cc0bd/reports/f8cb91d20eff4b298acf67bacb19b704/results.json build/release-1/new-report.html
```

Choose a new destination: the publisher refuses to overwrite a report edition.
Its JSON contains `trace_columns`; each case's `trace` is an array of rows in that
column order. These are selected original numerical operands, with repeated scope
prose omitted. The complete source periods and chronology remain the authority.
The HTML embeds its data and font, so reading and changing the playhead need no
network. Local artifact links require the files described below.

The final-source 36-hour demonstration is in `build/release-1/release-example`:
`summary.json` identifies its saved archive and `reproduction.zip` is portable.
Its unpacked `offline/` directory contains playback, all twenty saved Model topics,
the source, environment locks and standalone checker. Executed commands:

```
.venv/bin/python -I -S build/release-1/release-example/offline/check_bundle.py build/release-1/release-example/offline --out build/release-1/release-source/offline-check.json
.venv/bin/python build/release-1/release-example/offline/source/recompute.py build/release-1/release-example/offline/recorded-run.json.gz build/release-1/release-source/recomputation.json
```

The standalone audit passes 4,270 checks; the original-source numerical rerun has
zero different intervals. Use new output paths for further editions. A restored
runtime must satisfy the captured environment; numerical differences are reported
instead of assuming identical schedules from time-limited solves.

Preparing again creates a new immutable edition. It never overwrites a saved
experiment or changes its numerical inputs. Sites provides original playback,
new numerical repetitions and reproduction exports. Large numerical operands and
source capsules remain local under `runs/sites`; Git stores the protocol and compact
publication, not a backup of those operands.

This programme qualifies numerical behaviour and workflows. It does not establish
field reliability, autonomous robotic repair, annual maintenance costs, equipment
calibration or site profitability. Event seeds are not independent weather years;
numerical repetitions are not new environmental samples.

The next Release-2 package should preserve the outstanding study obligations,
investigate low-power observability and unsettled numerical comparisons, and carry
terminal condition/resources through longer windows. It then completes the hardware
family dispositions, shared infrastructure, commissioning, degradation, maintenance
and site/lifecycle comparisons. Release 3 supplies reproducible learning and held-out
qualification, then finishes the integrated product and participant comprehension.
