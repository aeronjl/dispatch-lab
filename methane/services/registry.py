"""Validated assembly of service models. Builders and effects have distinct interfaces."""

from dataclasses import asdict

from methane.services import CONTRACT_VERSION, SOURCE_IDENTITY
from methane.services.adapters import BUILDERS


def indexed(items, key):
    values = tuple(items)
    result = {getattr(value, key): value for value in values}
    if len(result) != len(values):
        raise ValueError(f"Duplicate {key}")
    return result


class Registry:
    def __init__(self, assets, interfaces, capabilities, resources, access, builders=None):
        self.assets = indexed(assets, "asset_id")
        self.interfaces = indexed(interfaces, "interface_id")
        self.capabilities = indexed(capabilities, "capability_id")
        self.resources = indexed(resources, "resource_id")
        self.access = access
        self.builders = dict(BUILDERS if builders is None else builders)
        for asset in self.assets.values():
            if not set(asset.capabilities) <= self.capabilities.keys():
                raise ValueError(f"{asset.asset_id}: unknown capability")
            self._resource("asset:" + asset.asset_id, "slot", "capacity")
            if asset.battery_resource:
                spec = self._resource(asset.battery_resource, "kWh", "stock")
                if asset.return_reserve_kwh > spec.capacity:
                    raise ValueError("Return reserve exceeds battery capacity")
            for quantity in asset.support_resources:
                self._resource(quantity.resource, quantity.unit, "capacity")
        for interface in self.interfaces.values():
            for key in interface.exclusive_resources:
                self._resource(key, "slot", "capacity")
        for cap in self.capabilities.values():
            for quantity in (*cap.consumables, *cap.hourly_consumables):
                self._resource(quantity.resource, quantity.unit, "stock")
            for quantity in cap.shared_resources:
                self._resource(quantity.resource, quantity.unit, "capacity")
        for edge in self.access.edges:
            if edge.resource_id:
                self._resource(edge.resource_id, "slot", "capacity")

    def _resource(self, key, unit, kind):
        value = self.resources.get(key)
        if value is None or value.unit != unit or value.kind != kind:
            raise ValueError(f"{key}: requires {kind} resource with unit {unit}")
        return value

    def build(self, order, asset_id, capability_id, context, starting_at=None, adapter_id=None):
        asset = self.assets[asset_id]
        if adapter_id is None:
            adapter_id = (
                "fixed-service-adapter/1"
                if asset.mobility == "fixed"
                else "mobile-service-adapter/1"
            )
        builder = self.builders[adapter_id]
        return builder(
            order,
            asset,
            self.interfaces[order.interface_id],
            self.capabilities[capability_id],
            context,
            starting_at=starting_at,
            access=self.access,
        )

    def manifest(self):
        return dict(
            schema_version=CONTRACT_VERSION,
            source=dict(SOURCE_IDENTITY),
            assets=[asdict(v) for v in self.assets.values()],
            interfaces=[asdict(v) for v in self.interfaces.values()],
            capabilities=[asdict(v) for v in self.capabilities.values()],
            resources=[asdict(v) for v in self.resources.values()],
            access=[asdict(v) for v in self.access.edges],
            builders=sorted(self.builders),
            timing="Decimal-hour task schedule; new observations/effects eligible at the next hourly decision boundary",
        )
