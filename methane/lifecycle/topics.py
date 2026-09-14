"""Illustrated explanations for explicit commissioning and maintenance hypotheses."""

from methane.lifecycle.families import FAMILIES


def topics(C, P, topic):
    def page(title, purpose, passages, limits, extra=()):
        return topic(
            title,
            "Deployment and lifecycle",
            [],
            [
                "lifecycle/topics.py",
                "lifecycle/learning.py",
                "lifecycle/configuration.py",
                "lifecycle/runtime.py",
                "lifecycle/accounting.py",
                "lifecycle/families.py",
                "lifecycle_reference.py",
                *extra,
            ],
            purpose,
            passages,
            limits,
            [
                "https://doi.org/10.1002/pip.2744",
                "https://www.energy.gov/cmei/fuels/technical-targets-proton-exchange-membrane-electrolysis",
            ],
        )

    return {
        "deployment": page(
            "Capacity arrives after acceptance",
            "A delivered machine is not yet an operating plant. Follow the work, acceptance and departure that make capacity available.",
            [
                P(
                    "Build a declared work package",
                    "This independent example installs an initially unavailable 500 kW array. Mobilisation, acceptance and departure each need one crew hour. Change installation effort and available crew time; hours are illustrative work requirements, not a measured construction-robot rate.",
                    [
                        C("work", "Installation work", 4, 1, 12, 1, "crew h"),
                        C("crew", "Daily project crew", 8, 1, 12, 1, "h"),
                    ],
                ),
                P(
                    "Acceptance can send work back",
                    "A failed attempt requires two rework hours and another acceptance attempt. No capacity is credited early. At most three attempts are allowed. A current access outage interrupts work without deleting progress; its end is not forecast to the executive.",
                    [
                        C("failed", "Failed acceptance attempts", 1, 0, 3, 1),
                        C("blocked", "Access unavailable from H2", 0, 0, 12, 1, "h"),
                    ],
                    "Available capacity = nameplate × accepted fraction",
                    [
                        (
                            "accepted",
                            "Recorded successful acceptance, eligible at the next hourly boundary.",
                        )
                    ],
                ),
                P(
                    "The support system has a bill",
                    "The fixture pays an additional project crew €80/h, one €300 callout, equipment hire €40/h, 2 kWh of external energy per work hour at €0.25/kWh and €500 materials. Equipment departs after acceptance. These invoices are capital work, separate from operating wear and fuel. Actual site designs can edit every rate.",
                ),
            ],
            "Declared sequential work, not certified commissioning, transport geometry or autonomous construction. A partly completed package remains a terminal obligation.",
        ),
        "condition": page(
            "Condition is observed, then acted on",
            "Age, a measured condition, a replacement procedure and confirmed restoration are different states.",
            [
                P(
                    "Choose an ageing hypothesis",
                    "Solar loses a linear fraction with calendar exposure, independently of cleaning. The PEM hypothesis increases specific electricity consumption in proportion to voltage growth. The example fixes operating activity when not isolated; it does not forecast remaining useful life.",
                    [
                        C(
                            "asset",
                            "Condition mechanism",
                            "electrolyser",
                            options=["electrolyser", "solar"],
                        ),
                        C("age", "Initial exposure", 40000, 0, 100000, 1000, "h"),
                        C("rate", "Reference rate multiplier", 1, 0, 2, 0.1),
                    ],
                    "PEM increase = rate × operating hours / reference voltage",
                    [
                        (
                            "operating hours",
                            "Elapsed productive hours; a separate configured start-equivalent allowance defaults to zero.",
                        )
                    ],
                ),
                P(
                    "Wait for an eligible observation",
                    "A declared condition channel samples hourly with uniform bounded noise. Communications and reporting delay determine what the executive can know. The channel is an assumption requiring equipment evidence, not a perfect hidden-health oracle.",
                    [
                        C("delay", "Observation delay", 1, 1, 6, 1, "h"),
                        C("noise", "Condition noise bound", 0.002, 0, 0.02, 0.001),
                        C("threshold", "Replacement threshold", 0.1, 0.02, 0.2, 0.01),
                    ],
                ),
                P(
                    "Spend stock, then verify",
                    "A two-hour human procedure requires a spare, reference, access and the dedicated crew. In this teaching case a procedure either always succeeds or never succeeds; this is a challenge choice, not a calibrated failure rate. Only a later reading confirms condition. Two failed verifications stop automatic repeats. A replacement cannot clear unrelated injected faults or surface damage.",
                    [
                        C(
                            "success",
                            "Procedure outcome challenge",
                            "succeeds",
                            options=["succeeds", "fails"],
                        )
                    ],
                ),
                P(
                    "Interpret the reference carefully",
                    "The solar 0.5%/year starting point represents a literature median. The PEM 4.8 mV/1,000 h at 1.9 V is DOE's continuous-operation 2022 status. Dynamic degradation, start damage and measurements are not calibrated here. Values beyond the reference's 10% end-of-life criterion are explicitly extrapolative challenges.",
                ),
            ],
            "A whole-asset reduced condition model with an assumed observation channel. Fixed activity in this essay does not establish coupled production or repair benefit.",
        ),
        "hardware": page(
            "What each hardware family can do",
            "A family describes equipment. A usable capability also needs an implemented effect, a compatible interface, support and evidence.",
            [
                P(
                    "Select a concrete effect",
                    "Explore all fourteen families. Available means a bounded model can be configured, not that a vendor machine can do the task at this plant. Unsupported flight, wall inspection, vegetation growth, sampling and autonomous manipulation remain unavailable.",
                    [C("family", "Hardware family", "row-cleaner", options=list(FAMILIES))],
                ),
                P(
                    "Remove a prerequisite",
                    "The eligibility screen preserves each missing prerequisite. The real execution adapter still checks present observations, resources, isolation and its own procedure. Providing all prerequisites cannot make an unimplemented mechanism available.",
                    [
                        C(
                            "support",
                            "Declared prerequisites",
                            "present",
                            options=["present", "missing"],
                        ),
                        C(
                            "automation",
                            "Requested mode",
                            "declared",
                            options=["declared", "autonomous"],
                        ),
                    ],
                ),
                P(
                    "Follow an available mechanism",
                    "Cleaning, prepared-contact inspection and bounded recovery are explained in their respective essays. Construction and deployable-array entries refer to declared human/assisted work packages. The robot-compatible module family has a human replacement baseline; autonomous insertion remains restricted. Catalogue restrictions are checked when assembling service assets.",
                ),
            ],
            "Feasibility literature is dated evidence, not a runtime grant. No universal robot, generic camera diagnosis or arbitrary repair probability fills a missing mechanism.",
        ),
        "maintenance": page(
            "Compare work across the same operating window",
            "A maintenance rule must earn its production and cost consequences under the same weather, initial condition and information.",
            [
                P(
                    "Run four matched policies",
                    "Calculate a coupled synthetic plant with no condition maintenance, a periodic schedule, a measured threshold, and a forecast-window rule. The forecast rule delays work toward a complete low-PV shift window. Existing plant and field services still consume shared power. The dedicated project crew and finite part stock remain explicit.",
                    [
                        C("hours", "Comparison window", 48, 24, 96, 24, "h"),
                        C("age", "Initial PEM operating exposure", 40000, 20000, 60000, 10000, "h"),
                    ],
                ),
                P(
                    "Challenge the decision boundary",
                    "Change replacement cost or forecast stress. Each policy sees the same initial assumptions and seeded observation channel. A short window can penalise work whose benefit arrives later; longer windows carry state rather than resetting it. The periodic interval is an accelerated 24-hour teaching schedule.",
                    [
                        C("part", "Replacement part assumption", 120000, 0, 180000, 10000, "EUR"),
                        C("stress", "Forecast bias", 0, -0.5, 0.5, 0.1),
                    ],
                ),
                P(
                    "Inspect the terminal obligations",
                    "Compare methane, energy, hydrogen, CO₂, thermal state, ending condition, spares and unverified work. Cash purchases, allocated cost and decision contribution are different views. No policy is required to win. There is no annual profitability inference or empirically calibrated failure prediction in this experiment.",
                ),
            ],
            "Synthetic bounded scheduling comparison; no learned policy and no claim of field realism. Solver time limits and any incomplete or failed case remain visible.",
            ["simulation.py", "dispatch.py"],
        ),
    }
