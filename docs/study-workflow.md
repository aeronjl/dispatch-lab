# Reusable experiments and editable reports

Open **Sites → Production studies**. Each study freezes the plant design, environment,
controller, seeds, purpose and application source. Start is a separate action.
Cancel retains committed hours; Resume uses the original source and last checkpoint.
New numerical repetition creates a new edition. Failed and incomplete cases stay visible.

## Templates

Open a study and choose **Save as experiment template**. Record its question,
comparison method and limitations. The template contains cases, saved design/weather
identities and a write-up structure, with empty findings. It contains no result or
checkpoint to masquerade as a new experiment.

Select a template from the study index, review its cases and freeze a new study.
To change plant parameters, save a revised design in Sites and substitute its ID
in the case editor. Environment compatibility is checked. Missing saved weather or
designs cause an error, never an unlabelled substitute. A new study uses the current
application; the template keeps the original source identity as historical context.
Its complete template snapshot travels in the new study and reproduction bundle.

## Runtime

The study page reports remaining simulated hours. After a partition is committed,
its wall time can estimate later work with the same configuration and controller.
Timings are not pooled across source versions or different controllers/configurations.
Older records without timings say that the estimate is unavailable.

Before starting, **Estimate runtime** accepts a measured local pilot rate in seconds
per simulated hour. This is an explicit assumption. The displayed 0.5–2× range is
a workload allowance, not a confidence interval. It includes measured partition
execution and saving, but excludes queueing, final reconciliation and exports.
Machine contention and solver difficulty can change it. Estimates do not affect dispatch.

## Write-ups

**Write-up & export** opens an editor for title, question, method, findings,
limitations and next questions. Publish freezes that narrative alongside the result.
The study index lists report editions; **Edit another edition** reopens a saved
interpretation. Revising an existing report keeps its numerical snapshot, even if
the study has subsequently progressed. To report new hours, publish from the study
again. Reports distinguish observations, estimates and retrospective truth through
the underlying recorded context; narrative claims are authored interpretations.

The HTML report is readable offline. A reproduction bundle contains recorded inputs,
source and permitted data; redistribution gaps remain explicit. Original editions
and physical traces are never overwritten by editing prose.
