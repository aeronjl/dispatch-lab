# Simulation-first interface

The plant illustration is the default full-viewport experience. Its SVG elements,
labels, units, geometry and linework remain unchanged. Future engineering work
must preserve that boundary unless a visual change is explicitly requested.

The only default controls around the illustration are a menu button and a compact
playback dock. The dock expands to reveal timeline, speed and reset. Hide controls
(or H while the canvas is focused) retreats the dock; the small menu affordance
and keyboard shortcuts remain available. Escape closes an open panel.

Selecting equipment opens an overlay inspector; it does not displace or scroll
the illustration. Solar selection still opens the existing detailed workspace.
Read-only plan loading updates the inspector without dimming the whole canvas.

The menu reveals run context, dates, policy, totals and the existing cost toggle.
Events, comparisons and retrospective truth have separate views within it.
Setup and analysis occupy separate screens, with a persistent return control.
Analysis contains report, experiment, archive and guide tabs. Navigating between
screens preserves the run and playhead; leaving the canvas pauses playback.

On narrow screens the diagram remains horizontally accessible and the menu offers
an equipment picker. The overlays scroll internally. Reduced-motion preferences
are respected, and hidden controls are removed from keyboard navigation.

Verification covers the full viewport, default hidden detail, retreat/reveal,
keyboard inspection, playhead preservation, separate screens, narrow access and
batch navigation. The original diagram screenshots are compared at their original
size and position, without updating the reference images. A source hash additionally
checks that every original plant SVG element and label remains intact.
