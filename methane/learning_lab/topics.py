"""Authored explanations bound to the training and deployment implementation."""


def topics(C, P, topic):
    def page(title, purpose, passages, limits):
        return topic(
            title,
            "Learning and autonomy",
            [],
            [
                "learning_lab/datasets.py",
                "learning_lab/estimators.py",
                "learning_lab/deployment.py",
                "learning_lab/reserves.py",
                "learning_lab/teaching.py",
                "learning_lab/fixtures.py",
                "learning_lab/topics.py",
                "learning_lab/workflow.py",
                "policy.py",
                "dispatch.py",
                "simulation.py",
            ],
            purpose,
            passages,
            limits,
        )

    return {
        "learning_data": page(
            "What the policy could know",
            "An observation dataset is a set of information boundaries, not a dump of simulator state.",
            [
                P(
                    "Freeze complete episodes",
                    "Training, validation and test episodes are declared before fitting. Adjacent hours stay together. Reusing the same site and overlapping weather window with a different controller or seed does not create a new independent holdout.",
                    [
                        C(
                            "overlap",
                            "Reuse a weather window across splits",
                            "no",
                            options=["no", "yes"],
                        )
                    ],
                ),
                P(
                    "A reading must have arrived",
                    "The packet keeps observations, estimates and published forecasts distinct. A condition measurement is absent until its availability boundary. Private fault types, repair outcomes and future recovery clocks never enter it.",
                    [
                        C("hour", "Decision boundary", 2, 0, 6, 1, "h"),
                        C("delay", "Measurement delay", 3, 0, 6, 1, "h"),
                    ],
                    "eligible = available_at ≤ decision_time",
                    [
                        (
                            "available_at",
                            "When this assumed channel becomes available, not when a later report was generated.",
                        )
                    ],
                ),
                P(
                    "Rebuild from the same sources",
                    "Saved datasets pin partition hashes, configuration, weather windows, original source, prices and sensor assumptions. Outcome labels occupy a separate scoring store. In Sites → Learning & policies, freeze episodes, inspect the port and reconstruct the dataset before training.",
                ),
            ],
            "This example constructs a delayed meter and episode registry. It is not empirical sensor validation; large datasets cannot make an assumed channel identifiable.",
        ),
        "estimators": page(
            "Estimate a channel before scheduling",
            "Compare a simple baseline, an adaptive estimate and a fitted model against genuinely separate episodes.",
            [
                P(
                    "Ask an identifiable question",
                    "This fixture predicts the next observed solar, condition or removable-surface channel. It cannot infer fault cause or remaining useful life. Service-duration training is also available from recorded clocks: unfinished jobs are explicitly censored, never labelled as completed work.",
                    [
                        C(
                            "task",
                            "Observed channel",
                            "solar_condition",
                            options=["solar_condition", "electrolyser_condition", "soiling", "pv"],
                        )
                    ],
                ),
                P(
                    "Fit only on training episodes",
                    "The fitted model uses four recorded features. Means and scales come from training; a declared ridge penalty controls coefficient size. Validation errors provide an empirical band. Test outcomes do not select weights or broaden the deployment domain.",
                    [
                        C("noise", "Assumed channel noise", 0.01, 0, 0.05, 0.005, "fraction"),
                        C("ridge", "Declared regularisation", 1.0, 0.01, 10.0, 0.01),
                    ],
                    "prediction = intercept + Σ weight × standardised_feature",
                    [("weight", "Coefficient fitted to training observations only.")],
                ),
                P(
                    "Read errors and exclusions together",
                    "Compare fixed, adaptive and fitted errors. The adaptive model learns only after a reading arrives; it resets between episodes. Missing inputs, no new condition reading, low solar excitation and unsupported feature ranges remain visible. Bands describe validation errors; they are not guaranteed coverage under changed equipment.",
                    [C("missing", "Missing condition messages", "no", options=["no", "yes"])],
                ),
            ],
            "Fixed-seed constructed observations exercise the same fitting path as saved studies. Predictive accuracy is not evidence of methane value or field identifiability. Completed-only duration regression is biased under censoring; use the existing duration survival model for that question.",
        ),
        "policies": page(
            "Give reserves an explicit purpose",
            "A richer policy earns its place through inspectable trade-offs, not an assumption that learning must win.",
            [
                P(
                    "Start from identical information",
                    "This six-hour planning example compares Greedy, methane MPC and economic MPC with the same state, forecast and prices. Each proposed trajectory passes the existing physical replay checks. Time limits and fallbacks remain part of the result.",
                    [
                        C("power", "Forecast power scale", 1.0, 0, 1.5, 0.1),
                        C("price", "Methane value", 1.0, 0, 5, 0.1, "EUR/kg"),
                    ],
                ),
                P(
                    "A reserve is a soft preference",
                    "Add saturating battery, feedstock and thermal shortfall penalties to the two MPC objectives. Hot or committed reactors have larger gas and heat needs; anticipated service demand adds to battery need. No preference overrides power, material or thermal bounds.",
                    [
                        C("reserve", "Battery target", 0.2, 0, 1, 0.05, "fraction"),
                        C("weight", "Normalised shortage penalty", 0.5, 0, 10, 0.1),
                    ],
                    "shortfall = max(0, target − inventory)",
                    [
                        (
                            "target",
                            "A declared mode-dependent need; inventory above it earns no additional reward.",
                        )
                    ],
                ),
                P(
                    "Contain the experimental policy",
                    "Registered artifacts pin weights, transforms, dataset and source. The first learned operational aid can change the first future PV estimate; current measured power is immutable. Invalid, missing, late or unsupported predictions retain the original policy. Reference availability, spares and unfinished work stay in the service executive; this process objective does not invent decisions to buy them.",
                ),
                P(
                    "Separate preference from expenditure",
                    "The reserve penalty is in the selected objective's units. It is not a cash expense or an ending-inventory sale. Ownership stays outside dispatch incentives. Compare actual production, variable cost, interventions, failures and terminal obligations in a matched operating study before claiming benefit.",
                ),
            ],
            "Bounded hourly predicted trajectories, not an RL-trained executive or a jointly optimal maintenance/construction policy. No universal safety or trust score; physical constraints remain in production kernels.",
        ),
    }
