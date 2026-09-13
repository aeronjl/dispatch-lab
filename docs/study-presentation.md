# Reading large studies

The Studies workspace uses a display projection of a saved publication. Python
copies the figures, comparisons, ending inventories, work-order summaries and
authored interpretation used by the screen. It does not recalculate outcomes.
Full service receipts and computational trajectories remain in the original
publication, signed case attempts and archived recordings.

Selecting **Inspect full service record** requests the original case, attempt and
controller. For a saved publication, the request checks both the attempt identifier
and its recorded integrity identity. A later attempt cannot replace that history.
The response also carries the edition, report and request generation; leaving the
panel or selecting another record prevents a late response from replacing the view.
Errors retain a route back to the case.

Completed-edition index counts come from the latest publication and are labelled
as published counts. A current worker or interrupted execution is shown separately
in the status. A withdrawal overrides both. Editions without publications retain
their existing current-attempt summary. Opening a running edition continues to
show its live progress; opening a specific report pins that publication.

## Preservation and caches

`methane/study_presentation.py` creates separate, sealed publication indexes and
display files. Each records the complete original report file's SHA-256; display
directories also identify the presentation implementation. Original report and
attempt files are never rewritten. Read-only restored stores can derive an
in-memory view without claiming it was saved.

Derived files become visible only after their bytes have been fully written.
Concurrent readers can produce the same view without seeing a partial file or
overwriting a conflicting record. This does not change the format of original
publications or case attempts.

The app caches verified immutable display records. Changes to the original or
derived file's modification time, size or inode invalidate the cache; subsequent
reads verify integrity and source binding again. Missing original reports are not
supplied from the cache. This is an interactive reading cache, not continuous
filesystem attestation against a same-stat malicious modification. Publication,
recorded archive inspection and bundle checks retain their original full-record
verification paths.

New offline HTML reports include selected metrics and inputs, linking the complete
original publication and individual case attempts. Bundle-relative links use the
restored directory structure. Older HTML and JSON reports remain unchanged.
The original report identity on a display projection is explicitly labelled as
the original identity; it is not presented as the hash of the reduced response.

## Verification scope

`tests/test_study_presentation.py` checks operand preservation, immutable originals,
caller isolation, corrupt or missing artifacts, publication/attempt identity,
read-only stores, targeted reads and offline links. Browser checks exercise pending,
failed and superseded service-record requests. Numerical simulation tests and
historical evidence retain their own source identities; a rendering improvement
does not certify a different numerical model.
