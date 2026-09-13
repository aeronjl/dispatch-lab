/* Illustrations consume measured steps; they never advance or modify the plant. */
function plantFlowState(plant, frame) {
    const active = value => value > 1e-6;
    const ratio = (value, capacity) => capacity > 0 ? Math.max(0, Math.min(1, value / capacity)) : 0;
    const charging = active(frame.charge_kw), discharging = active(frame.discharge_kw);
    const batteryDirection = charging ? 'charge' : discharging ? 'discharge' : 'idle';
    return {
        source: frame.pv_kw,
        solar: Math.max(0, frame.pv_kw - frame.curtailed_kw),
        load: frame.electrical_demand_kw,
        battery: charging ? frame.charge_kw : frame.discharge_kw,
        hydrogen: frame.h2_kg / plant.dt_hours,
        curtailment: frame.curtailed_kw,
        batteryDirection,
        solarLevel: ratio(frame.pv_kw, plant.solar_kw),
        loadLevel: ratio(frame.productive_kw, plant.electrolyser_kw),
        capacityLevel: ratio(frame.capacity_kw, plant.electrolyser_kw),
        batteryLevel: ratio(frame.battery_kwh, plant.battery_kwh),
        batteryPresent: plant.battery_kwh > 0,
        producing: active(frame.productive_kw),
        fault: frame.capacity_kw < plant.electrolyser_kw - 1e-6,
    };
}

function initialisePlantScene(element) {
    const plates = element.querySelector('[data-role="stack-plates"]');
    plates.innerHTML = Array.from({length:7}, (_, i) => {
        const x = 31 + i * 18;
        return `<g class="stack-plate" style="--plate-index:${i}">
            <path class="plate-front" d="M${x} 76H${x+11}V149H${x}Z"/>
            <path class="plate-side" d="M${x+11} 76L${x+23} 65V138L${x+11} 149Z M${x} 76L${x+12} 65H${x+23}L${x+11} 76Z"/>
            <rect class="plate-energy" x="${x+3}" y="84" width="5" height="56"/>
            <path d="M${x+3} 81H${x+8} M${x+3} 144H${x+8}"/>
        </g>`;
    }).join('');
    element.querySelector('[data-role="battery-cells"]').innerHTML = Array.from({length:3}, (_, i) => {
        const y = 31 + i * 27;
        return `<g><rect class="battery-module" x="36" y="${y}" width="76" height="20"/>
            <rect class="battery-fill" data-cell="${i}" x="39" y="${y+3}" width="0" height="14"/>
            <path d="M115 ${y+6}H118V${y+14}H115"/></g>`;
    }).join('');
}

function updatePlantScene(element, plant, frame, playback) {
    const visual = plantFlowState(plant, frame);
    const scene = element.querySelector('[data-role="plant-scene"]');
    const fmt = (v, digits = 0) => v.toLocaleString('en-GB', {minimumFractionDigits:digits, maximumFractionDigits:digits});
    const text = (key, value) => element.querySelectorAll(`[data-scene-field="${key}"]`).forEach(node => {node.textContent = value;});
    const part = name => element.querySelector(`[data-part="${name}"]`);
    scene.dataset.playing = String(playback.playing);
    // Visual cadence responds to throughput; playback speed remains the hourly clock's job.
    const limits = {source:plant.solar_kw, solar:plant.solar_kw,
        load:plant.electrolyser_kw + plant.start_energy_kwh / plant.dt_hours,
        battery:plant.battery_kwh * plant.battery_c_rate,
        hydrogen:plant.electrolyser_kw / plant.specific_energy_kwh_per_kg,
        curtailment:plant.solar_kw};
    for (const name of Object.keys(limits)) {
        const flow = element.querySelector(`[data-flow="${name}"]`);
        const fraction = limits[name] > 0 ? Math.min(1, visual[name] / limits[name]) : 0;
        flow.dataset.active = String(visual[name] > 1e-6);
        flow.style.setProperty('--flow-strength', `${1.5 + fraction * 3.5}`);
        flow.style.setProperty('--flow-time', `${3.2 - fraction * 2.4}s`);
        if (name === 'battery') flow.dataset.direction = visual.batteryDirection === 'discharge' ? 'discharge' : 'charge';
    }
    part('solar').style.setProperty('--solar-level', visual.solarLevel);
    part('solar').dataset.active = String(visual.source > 1e-6);
    part('stack').dataset.active = String(visual.producing);
    part('stack').dataset.fault = String(visual.fault);
    part('stack').style.setProperty('--reaction-time', `${2.5 - 1.7 * visual.loadLevel}s`);
    element.querySelectorAll('.stack-plate').forEach((plate, i) => {
        // A derating dims a proportional share of the illustrated stack.
        const available = Math.max(0, Math.min(1, visual.capacityLevel * 7 - i));
        plate.style.setProperty('--plate-level', visual.loadLevel * available);
        plate.style.opacity = .3 + .7 * available;
    });
    part('battery').dataset.absent = String(!visual.batteryPresent);
    element.querySelectorAll('[data-cell]').forEach(cell => {
        const tier = 2 - Number(cell.dataset.cell);
        const fill = Math.max(0, Math.min(1, visual.batteryLevel * 3 - tier));
        cell.setAttribute('width', (70 * fill).toFixed(2));
    });
    part('hydrogen').dataset.active = String(visual.producing);
    part('hydrogen').style.setProperty('--gas-time', `${3 - 2 * visual.loadLevel}s`);
    part('curtailment').dataset.active = String(visual.curtailment > 1e-6);
    text('solar-power', fmt(frame.pv_kw)); text('solar-flow', fmt(visual.solar));
    text('solar-caption', !frame.hour ? 'AWAITING FIRST STEP' : !plant.solar_kw ? 'NO SOLAR INSTALLED' : visual.source > 1e-6 ? `${fmt(visual.solarLevel * 100)}% OF NAMEPLATE` : 'NIGHT / NO GENERATION');
    text('load-flow', fmt(visual.load)); text('h2-flow', fmt(visual.hydrogen, 1));
    text('stack-load', fmt(visual.loadLevel * 100)); text('productive-power', fmt(frame.productive_kw));
    text('stack-state', frame.started ? 'STARTING' : visual.producing ? 'PRODUCING' : 'STANDBY');
    text('stack-capacity', `${visual.fault ? 'DERATED / ' : ''}${fmt(frame.capacity_kw)} kW AVAILABLE`);
    text('hydrogen-total', fmt(frame.hydrogen_kg, 1)); text('curtailed-power', fmt(frame.curtailed_kw));
    text('battery-direction', !visual.batteryPresent ? 'NO BATTERY' : visual.batteryDirection === 'idle' ? 'BATTERY IDLE' : visual.batteryDirection === 'charge' ? '↓ CHARGING' : '↑ DISCHARGING');
    text('battery-flow', fmt(visual.battery)); text('battery-soc', visual.batteryPresent ? fmt(visual.batteryLevel * 100) : '—');
    text('battery-energy', `${fmt(frame.battery_kwh)} / ${fmt(plant.battery_kwh)} kWh`);
    text('battery-loss', `LOSSES ${fmt(frame.battery_loss_kwh || 0, 1)} kWh / STEP`);
    text('motion-state', `${playback.playing ? 'FLOW ACTIVE' : 'MOTION PAUSED'} / HOUR ${String(frame.hour).padStart(3,'0')}`);
    let story;
    if (!frame.hour) {
        story = `The plant starts with ${fmt(frame.battery_kwh)} kWh stored. Play or step forward to see solar electricity move through the DC bus into the battery and electrolyser.`;
    } else {
        const parts = [visual.source > 1e-6 ? `Solar supplies ${fmt(visual.source)} kW.` : 'Solar is not generating in this hour.'];
        if (visual.batteryDirection === 'charge') parts.push(`${fmt(visual.battery)} kW goes into charging the battery.`);
        if (visual.batteryDirection === 'discharge') parts.push(`The battery supplies ${fmt(visual.battery)} kW to the DC bus.`);
        if (visual.producing) parts.push(`The electrolyser uses ${fmt(frame.productive_kw)} kW for production, making ${fmt(frame.h2_kg,1)} kg of hydrogen this hour.`);
        else parts.push('The electrolyser is off.');
        if (frame.started && frame.startup_kwh > 0) parts.push(`Starting also consumes ${fmt(frame.startup_kwh)} kWh.`);
        if (visual.curtailment > 1e-6) parts.push(`${fmt(visual.curtailment)} kW of solar is left unused.`);
        if (visual.fault) parts.push(`A capacity fault limits the stack to ${fmt(frame.capacity_kw)} kW.`);
        story = parts.join(' ');
    }
    element.querySelector('[data-role="plant-story"]').textContent = story;
    element.querySelector('[data-role="plant-drawing"]').setAttribute('aria-label', story);
}

if (typeof module !== 'undefined' && module.exports) module.exports = {plantFlowState};
