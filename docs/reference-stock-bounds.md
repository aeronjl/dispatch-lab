# Stock boundaries in independent replay

Independent checker version 2 reports stock-bound violations as numerical
overruns in the resource's units. It retains the declared tolerance
`1e-5 + 1e-8 × max(1, |expected|)`. The expected boundary error is zero. No stock
is clamped, credited or changed by this check.

The retained 240-hour Greedy run `eb49ea26be5f1158` exposed the distinction at H184.
Its recorded old-brush disposal was 833.3333333333935 m². Decimal replay of the
earlier rounded event operands left 833.333333333380961 m², so the replay briefly
reached −1.2539×10⁻¹¹ m². The runtime balance reached zero. Version 1's exact
Boolean comparison converted that rounding residual into a failed condition
with residual −1 and no resource unit. All other 92,794 independent checks passed.

Version 2 measures the actual boundary error, then applies the existing
numerical tolerance. Tests also reject real 0.001 m² deficits and excesses.
The original failed audit is retained; corrected audits have a new checker
identity and separate artifacts. New calibration editions may use the separately
qualified original observations, with their original numerical source, unchanged
candidate models and original availability cutoff. They do not rewrite the
original physical trace or retroactively change the original audit.

This is numerical verification of recorded resource accounting. It does not
establish physical brush life, measurement precision or field calibration.
