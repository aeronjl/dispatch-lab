"""Named, editable learning assumptions; no supplier throughput or service quotation."""

from dataclasses import replace

from methane.lifecycle.configuration import validate
from methane.services.configuration import ServiceSystem


def illustrative(config, *, commission=True, aged=False, policy="condition"):
    p, c = config.plant, config.costs
    packages = []
    if commission:
        for key, asset, fraction, dependencies in (
            ("array-first", "solar", 0.5, []),
            ("battery-install", "battery", 1, ["array-first"]),
            ("electrolyser-install", "electrolyser", 1, ["battery-install"]),
            ("reactor-install", "reactor", 1, ["electrolyser-install"]),
            ("array-rest", "solar", 0.5, ["reactor-install"]),
        ):
            packages.append(
                dict(
                    id=key,
                    asset=asset,
                    fraction=fraction,
                    depends_on=dependencies,
                    method="prepared-array" if asset == "solar" else "manual",
                    installation_hours=4,
                    equipment_eur_per_hour=40,
                    equipment_energy_kwh_per_hour=2,
                    external_energy_eur_per_kwh=0.25,
                    installation_material_eur=500,
                    evidence="release-two/work-package-fixture: illustrative crew/equipment work; no calibrated automated deployment rate",
                )
            )
    options = validate(
        dict(
            packages=packages,
            maintenance_policy=policy,
            conditions=[
                dict(
                    asset="solar",
                    initial_calendar_hours=20 * 8766 if aged else 0,
                    replacement_part_eur=p.solar_kw * c.solar_eur_per_kw,
                    evidence="jordan-2016/median-crystalline-silicon: 0.5%/year reduced linear loss; full-array part price uses existing illustrative capital, no quotation",
                ),
                dict(
                    asset="electrolyser",
                    initial_operating_hours=45000 if aged else 0,
                    replacement_part_eur=p.electrolyser_kw
                    * c.electrolyser_eur_per_kw
                    * c.stack_share,
                    evidence="doe-pem-targets/2022-status: 4.8 mV/1000 h at 1.9 V; equivalent SEC growth, not a calibrated dynamic PEM stack",
                ),
            ],
            evidence_ids=[
                "jordan-2016/pip2744",
                "doe-pem-targets/2022-status",
                "release-two/work-package-fixture",
            ],
        )
    )
    return replace(
        config,
        lifecycle=options,
        field_operations=replace(config.field_operations, enabled=True),
        service_system=replace(
            config.service_system or ServiceSystem(), cleaning_model="section-optical/1"
        ),
    )
