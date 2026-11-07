# Human interface session

Status: staged protocol for the principal or another human operator. Completed
human sessions n=0. No usability outcome or native SAS comparison is claimed.
Automated fixture, API and CLI checks are separate evidence. Record the tested
commit, source digest and full verification receipt before beginning.

Use the local web workbench and the two prepared first-party showcase documents.
The assistant pane stays off; these tasks require no external service. Planned
session length is about 20 minutes. A facilitator may explain where the workbench
is, then observe without supplying the expected answer. Capture the operator's
interpretation before consulting the checks below.

From the repository, start the workbench with:

```sh
.venv/bin/python -m saschi serve --host 127.0.0.1 --port 8070
```

Open http://127.0.0.1:8070. The final preparation record under
telemetry/format-phases-20261103 identifies the compared and uncompared original
showcase files and their source binding. An agent opening the browser or taking
a screenshot does not count as a human session.

For an interactive task sheet, prepare a fresh first-party session:

```sh
.venv/bin/python tools/prepare_interface_session.py --output telemetry/human-session
```

Open `telemetry/human-session/index.html` in a browser. It provides the nine tasks,
copyable source, paired comparison documents, facilitator checks and an explicit
JSON observation export. Notes remain in the page until exported; reload clears
them. The preparation manifest records the source digest. Match that digest to
the current full verification receipt before testing. Preparation does not count
as a completed session, and generated documents do not establish browser layout
or keyboard usability.

Receipt comparison states distinguish `not requested`, `not reached`, `failed`
and `passed`. A requested check stays `not reached` if execution or an earlier
check stops the job. A check that starts but cannot read or validate its expected
artifact is `failed`. The Run stage and showcase show logical report text;
the Compare stage lists each recorded comparison separately.

| Task | Human action | Facilitator check after the attempt |
| --- | --- | --- |
| Find an example | Choose a shelf program and explain what Run treatment will do | Selected source and expected operation are discoverable |
| Read uncompared success | Paste examples/date_profile.sas, run it and explain which checks occurred | Accepted execution is distinguishable from a requested comparison; R availability is separate |
| Compare the evidence wording | Open the prepared uncompared and compared showcase documents | The operator distinguishes not requested from passed and does not infer a per-job R comparison |
| Find a formatted result | Paste examples/numeric_pictures.sas and locate the09/99 output difference | The operator can find stored numeric values and logical report text, or records a discoverability failure |
| Read a callback report | Paste examples/week_callbacks.sas and explain the blank repeated customer cells and date window | Repeated observations remain visible and the declared logical report is understandable |
| Understand refusal | In the date fixture change weekdate37 to weekdate50, then run again | The current failure, source location and reason are visible; no earlier success is mistaken for the current result |
| Recover | Restore the valid width and rerun | The new successful job and its evidence state are clear |
| Check job-local presentation | Run a valid fixture without its TITLE statement after a titled job | A previous job's title is not mistaken for current output |
| Use the keyboard and zoom | Repeat source entry, running and result inspection without a mouse; resize and increase zoom | Focus, reading order, diagnostics and evidence text remain usable |

One observation record per task:

- Tested commit, source digest and full verification receipt:
- Surface/browser/version, window size, zoom and input method:
- Task:
- Operator's interpretation, quoted only with permission:
- Completed without help, completed with help, or not completed:
- Time or blocking point:
- Actual wording, navigation or visual defect:
- Evidence reference, if captured with permission:
- Candidate fix and priority, explicitly an inference:

Keep credentials and unrelated personal material out of captures. Report the
observed n and task outcomes; one session does not establish a population success
rate. TUI testing is a separate later session. Record its optional rich setup
and actual outcome; web and CLI checks do not establish TUI usability.
