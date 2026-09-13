"""Bounded procedure choices declared at the original observation boundary.

Compatibility means a declared contact or work surface. It does not mean equal
measurement quality, cleaning efficacy, cost or physical outcome. This module
builds recipes only; it neither samples an inspection nor applies a treatment.
"""

from dataclasses import replace

from methane.services.coupling import identity

VERSION = "recorded-compatible-procedures/1"
CONTACT = "read-trip-contact"
CLEANING = ("clean-section", "portable-clean-section")


def identifier(asset, capability, interface):
    return identity(dict(asset=asset, capability=capability, interface=interface))


def capture(runtime, original):
    """Keep only installed, explicitly modelled alternatives for this request.

    An unavailable installed asset stays visible with its original reason. A
    missing asset is not added. Resource, current-power, shift and whole-return
    checks run again for the requested start through the normal planning port.
    """
    action = original.order.action
    if action != CONTACT and action not in CLEANING:
        return []
    compatible = (CONTACT,) if action == CONTACT else CLEANING
    result = []
    for asset in runtime.registry.assets.values():
        for key in asset.capabilities:
            cap = runtime.registry.capabilities[key]
            if cap.action not in compatible:
                continue
            for face in runtime.registry.interfaces.values():
                # A surface capability's duration belongs to its named section.
                # Matching only an action would wrongly reuse another row's
                # area/rate recipe on this target (or offer a no-op substitute).
                if cap.action in CLEANING:
                    prefix = "cleaning/" if cap.action == "clean-section" else "portable-cleaning/"
                    if key != prefix + face.target_asset_id:
                        continue
                if (
                    face.target_asset_id != original.interface.target_asset_id
                    or cap.action not in face.actions
                    or (asset, cap, face)
                    == (original.asset, original.capability, original.interface)
                ):
                    continue
                entry = dict(
                    procedure_id=identifier(asset.asset_id, key, face.interface_id),
                    asset_id=asset.asset_id,
                    capability_id=key,
                    interface_id=face.interface_id,
                    action=cap.action,
                    implementation_id=cap.implementation_id,
                    label=asset.archetype + " · " + cap.implementation_id,
                    scope=(
                        "The same declared trip contact, using this reader's channel, "
                        "references and travel. Shared contact errors remain possible. "
                        "No finding or recovery is credited by this comparison."
                        if action == CONTACT
                        else "The same array section with a different registered treatment. "
                        "Coverage, loose/adhered removal, brush use, water and crew time "
                        "follow that procedure. Permanent damage is unchanged."
                    ),
                    plan=None,
                    unavailable=None,
                )
                try:
                    if not runtime._available(asset.asset_id):
                        raise ValueError("Asset disabled, occupied or awaiting retrieval")
                    work = replace(
                        original.order, action=cap.action, interface_id=face.interface_id
                    )
                    plan = runtime.registry.build(work, asset.asset_id, key, runtime._context)
                    if cap.action == "portable-clean-section":
                        from methane.services.portable import prepare

                        plan = prepare(plan, runtime.options)
                    entry["plan"] = plan.to_dict()
                except (ValueError, KeyError) as exc:
                    entry["unavailable"] = str(exc)
                result.append(entry)
    return result


def selected(snapshot, order_id, procedure_id):
    """Resolve a saved choice; never rebuild original options from current code."""
    choices = snapshot.get("procedure_choices")
    if choices is None:
        raise ValueError(
            "Compatible procedures were not saved at this decision. "
            "Current equipment definitions cannot reconstruct original alternatives."
        )
    if not isinstance(order_id, str) or not isinstance(procedure_id, str):
        raise ValueError("Select a recorded work order and procedure identifier")
    choice = next((c for c in choices.get(order_id, ()) if c["procedure_id"] == procedure_id), None)
    if choice is None:
        raise ValueError("This procedure was not an installed compatible choice at this decision")
    return choice
