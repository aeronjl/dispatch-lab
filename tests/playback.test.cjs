const {test} = require('node:test');
const assert = require('node:assert/strict');
const {createPlaybackClock, frameAt} = require('../assets/playback.js');

function harness(duration = 72) {
    let time = 0, callback = null, changes = [], frames = [];
    const clock = createPlaybackClock({duration, onChange:s => changes.push(s), onFrame:s => frames.push(s), now:() => time,
        request:fn => { callback = fn; return 1; }, cancel:() => { callback = null; }});
    return {clock, changes, frames, advance(ms) { time += ms; const fn = callback; callback = null; if (fn) fn(time); }};
}

test('visual frames share the clock without emitting false completed intervals', () => {
    const {clock, advance, changes, frames} = harness(2);
    clock.play(); advance(250);
    assert.equal(changes.length, 1);
    assert.equal(frames.at(-1).fraction, .25);
    clock.pause(); const frozen = clock.visualSnapshot();
    advance(10000); assert.deepEqual(clock.visualSnapshot(), frozen);
    clock.setSpeed(2); clock.play(); advance(250);
    assert.equal(frames.at(-1).fraction, .75);
    clock.seek(1); assert.equal(frames.at(-1).fraction, 0);
    clock.play(); advance(500);
    assert.deepEqual(frames.at(-1), {hour:2, speed:2, playing:false, duration:2, fraction:0});
    const count=frames.length;clock.destroy();advance(1000);assert.equal(frames.length,count);
});

test('1× advances one hour per second and pause preserves partial elapsed time', () => {
    const {clock, advance} = harness();
    clock.play(); advance(1500); assert.equal(clock.snapshot().hour, 1);
    clock.pause(); advance(10000); assert.equal(clock.snapshot().hour, 1);
    clock.play(); advance(500); assert.equal(clock.snapshot().hour, 2);
});

test('all six speed settings advance at their stated rate', () => {
    for (const speed of [0.25, 0.5, 1, 2, 4, 8]) {
        const {clock, advance} = harness();
        clock.setSpeed(speed); clock.play(); advance(4000);
        assert.equal(clock.snapshot().hour, speed * 4);
    }
});

test('speed changes preserve progress, including a fractional hour', () => {
    const {clock, advance} = harness();
    clock.play(); advance(500); clock.setSpeed(2); advance(250);
    assert.equal(clock.snapshot().hour, 1);
    clock.play(); advance(500); assert.equal(clock.snapshot().hour, 2);
});

test('seek and step pause immediately and clamp at both ends', () => {
    const {clock, advance} = harness(48);
    clock.play(); clock.seek(20); advance(10000);
    assert.equal(clock.snapshot().hour, 20); assert.equal(clock.snapshot().playing, false);
    clock.step(-1); assert.equal(clock.snapshot().hour, 19);
    clock.seek(-5); clock.step(-1); assert.equal(clock.snapshot().hour, 0);
    clock.seek(500); clock.step(1); assert.equal(clock.snapshot().hour, 48);
});

test('ends exactly, stops the clock, and replays from the beginning', () => {
    const {clock, advance} = harness(48);
    clock.setSpeed(8); clock.seek(47); clock.play(); advance(1000);
    assert.equal(clock.snapshot().hour, 48); assert.equal(clock.snapshot().playing, false);
    clock.play(); assert.equal(clock.snapshot().hour, 0); advance(125);
    assert.equal(clock.snapshot().hour, 1);
});

test('loading a new run clears the cursor and pauses, preserving the selected speed', () => {
    const {clock, advance} = harness();
    clock.setSpeed(4); clock.play(); advance(2000); clock.reset(240); advance(1000);
    assert.deepEqual(clock.snapshot(), {hour:0, speed:4, playing:false, duration:240});
    clock.play(); advance(1000); assert.equal(clock.snapshot().hour, 4);
    clock.destroy(); advance(1000); assert.equal(clock.snapshot().hour, 4);
});

const result = {plant:{battery_kwh:100, initial_soc:.5, electrolyser_kw:100}, records:{
    Greedy:[{battery_kwh:40,h2_kg:1,started:1,productive_kw:55},
        {battery_kwh:30,h2_kg:2,started:0,productive_kw:100}],
    'Forecast MPC':[{battery_kwh:60,h2_kg:0,started:0,productive_kw:0},
        {battery_kwh:50,h2_kg:1,started:1,productive_kw:55}],
}};

test('zero is initial inventory; hourly totals contain no future production', () => {
    const before = JSON.stringify(result);
    assert.equal(frameAt(result, 0, 'Greedy').battery_kwh, 50);
    assert.equal(frameAt(result, 0, 'Greedy').hydrogen_kg, 0);
    const frame = frameAt(result, 1, 'Greedy');
    assert.equal(frame.hydrogen_kg, 1); assert.equal(frame.starts, 1);
    assert.equal(frame.soc, 40); assert.equal(frame.load, 55);
    assert.equal(frameAt(result, 2, 'Greedy').hydrogen_kg, 3);
    assert.equal(frameAt(result, 1, 'Forecast MPC').hydrogen_kg, 0);
    assert.equal(JSON.stringify(result), before);
});

test('no battery and no solar do not produce NaN or invent inventory', () => {
    const empty = structuredClone(result);
    empty.plant.battery_kwh = 0;
    assert.equal(frameAt(empty, 0, 'Greedy').battery_kwh, 0);
    assert.equal(frameAt(empty, 0, 'Greedy').soc, 0);
    assert.equal(frameAt(empty, 0, 'Greedy').pv_kw, 0);
});

const {plantFlowState} = require('../assets/plant-scene.js');
const scenePlant = {solar_kw:1000, battery_kwh:800, battery_c_rate:.5,
    electrolyser_kw:450, dt_hours:1, specific_energy_kwh_per_kg:55};
const sceneFrame = {pv_kw:800, curtailed_kw:100, electrical_demand_kw:450,
    productive_kw:450, capacity_kw:450, charge_kw:250, discharge_kw:0,
    battery_kwh:400, h2_kg:450/55};

test('illustrated branches conserve power through the solar split and DC bus', () => {
    const v = plantFlowState(scenePlant, sceneFrame);
    assert.equal(v.source, v.solar + v.curtailment);
    assert.equal(v.solar, v.load + v.battery);
    assert.equal(v.batteryDirection, 'charge');
    assert.equal(v.batteryLevel, .5);
    assert.equal(v.hydrogen, 450/55);
});

test('discharging reverses the battery branch and supplements available solar', () => {
    const v = plantFlowState(scenePlant, {...sceneFrame, pv_kw:200, curtailed_kw:0,
        charge_kw:0, discharge_kw:250});
    assert.equal(v.batteryDirection, 'discharge');
    assert.equal(v.solar + v.battery, v.load);
    assert.equal(v.producing, true);
});

test('nighttime idle has no active flows, even with energy in the battery', () => {
    const v = plantFlowState(scenePlant, {...sceneFrame, pv_kw:0, curtailed_kw:0,
        charge_kw:0, discharge_kw:0, electrical_demand_kw:0, productive_kw:0, h2_kg:0});
    for (const key of ['source','solar','load','battery','hydrogen','curtailment']) assert.equal(v[key], 0);
    assert.equal(v.batteryLevel, .5); assert.equal(v.batteryDirection, 'idle');
    assert.equal(v.producing, false);
});

test('all unused solar bypasses the DC bus and absent batteries do not fill', () => {
    const v = plantFlowState({...scenePlant, battery_kwh:0}, {...sceneFrame,
        curtailed_kw:800, battery_kwh:0, charge_kw:0, electrical_demand_kw:0, productive_kw:0,h2_kg:0});
    assert.equal(v.solar, 0); assert.equal(v.curtailment, v.source);
    assert.equal(v.batteryPresent, false); assert.equal(v.batteryLevel, 0);
});

test('fault dimming and productive activity use measured capacity and load', () => {
    const v = plantFlowState(scenePlant, {...sceneFrame, capacity_kw:135, productive_kw:135,
        electrical_demand_kw:175, h2_kg:135/55});
    assert.equal(v.fault, true); assert.equal(v.capacityLevel, .3);
    assert.equal(v.loadLevel, .3); assert.equal(v.load, 175);
    assert.equal(v.hydrogen, 135/55);
});
