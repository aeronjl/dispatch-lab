"""Authored service essays for the existing bounded mechanisms, not future families."""


def topics(C, P, topic):
    def page(title, files, purpose, passages, limits):
        return topic(
            title, "Field services", [], ["service_learning.py", *files], purpose, passages, limits
        )

    return {
        "cleaning": page(
            "Cleaning changes a surface, not a fault",
            ["services/surface.py", "services/optical.py"],
            "A cleaner changes optical loss only where it actually travels. More transmitted light may still be clipped or curtailed.",
            [
                P(
                    "Follow the treated area",
                    "Change the treated fraction of a 100 m² section. Untreated material remains. An interrupted mission retains the area already cleaned and the resources already spent.",
                    [
                        C("coverage", "Area treated", 0.6, 0, 1, 0.05),
                        C("loose", "Loose loss fraction", 0.12, 0, 0.3, 0.01),
                    ],
                ),
                P(
                    "Separate removable material from damage",
                    "Dry brushing removes a fraction of loose material. The wet fixture also removes 75% of the adhered material on the treated area. Neither repairs permanent damage. The fixture starts with 8% adhered loss and 3% damage.",
                    [
                        C("efficacy", "Loose material removed", 0.8, 0, 1, 0.05),
                        C("method", "Treatment", "dry", options=["dry", "wet"]),
                    ],
                    "Transmission = (1 − loose) × (1 − adhered) × (1 − damage)",
                    [("damage", "Permanent optical loss remains after this treatment.")],
                ),
                P(
                    "A mission needs support",
                    "Executed wet cleaning consumes its registered water and operator time; dry work consumes energy and brush life. Wind, rain, access, energy, consumables and return travel can restrict dispatch. This isolated surface calculation does not estimate those mission costs or methane benefit.",
                ),
            ],
            "Illustrative section-level optical losses and ideal surface monitoring. No string electrical faults, geometric dirt map or empirically calibrated cleaning yield.",
        ),
        "inspection": page(
            "What an inspection can actually reveal",
            ["services/inspection.py"],
            "A prepared reader measures a contact and its references. It cannot see inside every component or identify arbitrary damage.",
            [
                P(
                    "Read the measurement chain",
                    "The seeded acquisition adds the same offset to signal, zero and span, plus independently drawn bounded channel noise. Reference checks can isolate a drifting reader.",
                    [
                        C("signal", "Contact signal", 24, 0, 24, 1, "V"),
                        C("offset", "Reader offset", 0, -5, 5, 0.25, "V"),
                        C("noise", "Noise standard deviation", 0.1, 0, 2, 0.1, "V"),
                    ],
                    "Corrected = 24 × (signal − zero) / (span − zero)",
                    [
                        ("zero", "Measured zero reference, not an assumed fault label."),
                        ("span", "Measured span reference against the declared 24 V reference."),
                    ],
                ),
                P(
                    "Availability is part of the evidence",
                    "Move the decision clock. A later report cannot affect an earlier decision. Dropout means unavailable evidence, not a healthy contact.",
                    [
                        C("delay", "Report delay", 1, 0, 4, 1, "h"),
                        C("clock", "Decision clock", 1, 0, 5, 1, "h"),
                        C("dropout", "Dropout", "no", options=["no", "yes"]),
                    ],
                ),
                P(
                    "Agreement has limits",
                    "Two readers sharing one contact do not provide independent evidence about the contact itself. Both can agree on a stuck signal. Accessible and enclosed interfaces have different available actions; inspection does not grant physical repair capability.",
                ),
            ],
            "Prepared contact and reference reader only. Not thermal imaging, acoustic localisation, gas-leak diagnosis or certified safety instrumentation. Retrospective fixture inputs are shown separately from eligible observations.",
        ),
        "recovery": page(
            "Repair is followed by evidence",
            [
                "services/obligation_recovery.py",
                "services/verification.py",
                "services/procedures.py",
            ],
            "A bounded remedy changes the physical system only when its registered prerequisites and execution permit it. Operation must then establish recovery.",
            [
                P(
                    "Try a complete service episode",
                    "Calculate the synthetic coupled example: a capacity loss, a qualified human module replacement and measured operating tests. Compare a successful procedure, an unsuccessful procedure and power that disappears at H14.",
                    [
                        C(
                            "case",
                            "Service scenario",
                            "successful-procedure",
                            options=["successful-procedure", "failed-procedure", "power-shortage"],
                        )
                    ],
                ),
                P(
                    "One appointment is not the whole deadline",
                    "Version 5 fixes a finite deadline from diagnosis or a separate completed mission. Each appointment tests one upward capacity increment using the current forecast and shared electrical resources. Successful tracking must accumulate across the required intervals. Change the maximum wait; an impossible schedule stays unresolved.",
                    [C("deadline", "Maximum verification wait", 24, 4, 48, 1, "h")],
                ),
                P(
                    "Recover, remain degraded, or escalate",
                    "Power-blocked tests are inconclusive. Repeated measured shortfalls support bounded follow-up; a new remedy needs its own resources and receipt. Missed obligations escalate and remain recorded. Reset is restricted to compatible trips; module replacement to compatible damage; flow calibration to the supported sensor channel. No general-purpose robotic repair is implied.",
                ),
            ],
            "Hourly synthetic workflow, assumed repair outcomes and human service capability. No empirical repair rate, thermal calibration or safety certification. Earlier policy versions retain their original deadline semantics.",
        ),
        "charging": page(
            "Reserve energy for work and return",
            ["services/charging.py"],
            "Robot energy is a separate inventory. Charging consumes real plant electricity and does not instantly make a mission feasible.",
            [
                P(
                    "Charge before the opportunity disappears",
                    "This three-hour fixture has sunlight only in H0. A rover is connected then and consumes its declared work energy at H2. The dock is capped at 10 kW. Calculate a feasible plan or inspect why the requirement cannot be met.",
                    [
                        C("power", "H0 available PV", 10, 0, 20, 1, "kW"),
                        C("initial", "Initial rover energy", 0, 0, 10, 0.5, "kWh"),
                        C("use", "Mission energy", 6, 0, 10, 0.5, "kWh"),
                    ],
                ),
                P(
                    "Keep both sides of the balance",
                    "The bus supplies more energy than reaches the rover. Charging is credited at interval end; it cannot finance a departure at that interval start. Shared dock slots and physical availability also constrain full plant operation.",
                    [C("efficiency", "Charging efficiency", 0.8, 0.5, 1, 0.05)],
                    "Ending = initial + bus input × efficiency − mission use",
                    [("efficiency", "Conversion from bus electricity to stored robot energy.")],
                ),
                P(
                    "Return remains an obligation",
                    "Full service plans reserve return travel and support. A stranded robot requires a compatible retrieval or remote charging action. The present dock implementation uses available PV, not plant-battery discharge in darkness; the teaching example preserves that boundary.",
                ),
            ],
            "One rover, one dock and an authored departure. No new fleet routing or battery ageing mechanism. Solver limitations remain visible.",
        ),
        "logistics": page(
            "A service system has finite resources",
            ["services/resources.py", "services/support.py", "services/visits.py"],
            "Spares, crew time and access can be the binding constraints even when a technically compatible repair exists.",
            [
                P(
                    "A delivery and a reservation are different events",
                    "Two tasks request a kit and the single crew at H1 and H3. Move a delivery and change the initial stock. Deliveries are accepted against capacity before that hour’s task request; rejected items remain recorded.",
                    [
                        C("stock", "Initial kits", 1, 0, 5, 1, "kit"),
                        C("delivery", "Delivery quantity", 2, 0, 7, 1, "kit"),
                        C("arrival", "Delivery hour", 2, 0, 6, 1, "h"),
                    ],
                ),
                P(
                    "One crew cannot be in two places",
                    "Lengthen a task. Half-open reservations allow a second task exactly when the first ends. An overlap blocks the later request atomically: it must not consume a kit while failing to reserve a crew.",
                    [C("duration", "Task duration", 2, 1, 4, 1, "h")],
                ),
                P(
                    "Account for people and infrastructure",
                    "Full missions add shift calendars, lead time, travel, remote operator availability, route access, replenishment and compatible retrieval. Shared visits can avoid some travel, while a dock or communications failure can disable several capabilities together. Remote hours and physical visits are reported separately.",
                ),
            ],
            "This isolated resource ledger uses two fixed appointments and does not silently reschedule failures. Broader logistics durations and support availability remain disclosed assumptions.",
        ),
        "service_costs": page(
            "Three views of the same service work",
            ["service_economics.py", "services/pricing.py"],
            "Allocated period cost, decision cost and expenditure answer different questions. Adding them together would double-count service costs.",
            [
                P(
                    "Reprice a fixed teaching trace",
                    "The fixed quantities are four rover-hours, one visit, three crew-hours, half an hour of remote assistance and one replacement part over a 24-hour installed period. Change prices without changing those quantities.",
                    [
                        C("crew_price", "Crew price", 80, 0, 200, 5, "EUR/h"),
                        C("part_price", "Replacement part", 2500, 0, 5000, 100, "EUR"),
                    ],
                ),
                P(
                    "Ownership is not a dispatch incentive",
                    "The replaceable capital share is excluded from body ownership. Allocated replacement uses the largest calendar, usage or consumed-part allowance. Decision cost uses the largest usage or consumed-part amount. Procurement is a separate expenditure view.",
                    [
                        C("wear", "Rover wear proxy", 2, 0, 50, 1, "EUR/h"),
                        C("life", "Ownership life", 8, 1, 20, 1, "years"),
                        C("purchase", "Purchase at period start", "no", options=["no", "yes"]),
                    ],
                ),
                P(
                    "Do not charge the physical consequence again",
                    "Service electricity is already withdrawn from the plant bus; production consequences already appear in the trace. Neither is added again as purchased off-grid electricity or hypothetical lost methane. A zero-output unit cost remains undefined in plant reports; unknown quotes remain unpriced.",
                ),
            ],
            "Illustrative fixed quantities and prices, not invoices or measured ownership economics. Changing economic dispatch assumptions requires a new run.",
        ),
        "service_uncertainty": page(
            "Learn from elapsed work without seeing the outcome",
            ["duration_population.py"],
            "An installed asset can be persistently slower than expected, while individual jobs still vary. The model keeps these sources of uncertainty separate.",
            [
                P(
                    "An unfinished job is evidence",
                    "The one-hour nominal jobs share an editable observed elapsed duration. A completed job gives a duration; an unfinished job gives a lower bound. Move the clock to reveal only available packets.",
                    [
                        C("duration", "Observed elapsed duration", 1.2, 0.1, 2.5, 0.1, "h"),
                        C("jobs", "Recorded jobs", 3, 0, 6, 1),
                        C("censored", "Jobs unfinished", "no", options=["no", "yes"]),
                        C("clock", "Decision clock", 3, 0, 7, 1, "h"),
                    ],
                ),
                P(
                    "Update the equipment estimate",
                    "The illustrative prior uses equally weighted equipment factors 0.75, 1, 1.25 and 1.5, with a fresh uniform job multiplier from 0.8 to 1.2. Correlated phases from one job count once. The chart shows posterior weights, not measured population frequencies.",
                ),
                P(
                    "Recognise when the model does not apply",
                    "Observations outside the declared support are visible and prevent adaptive candidates from claiming feasibility. They do not silently widen bounds or become repaired-equipment truth. The fitting workflow supports held-out observations, but no matched field dataset has calibrated these factors.",
                ),
            ],
            "Finite-grid illustrative duration inference. Not remaining useful life, failure-frequency learning or a field reliability model.",
        ),
    }
