/* A clock over completed hourly states. Speed changes never alter the physical model. */
function createPlaybackClock({duration, onChange, onFrame = () => {}, now = () => performance.now(),
    request = fn => requestAnimationFrame(fn), cancel = id => cancelAnimationFrame(id)}) {
    let hour = 0, speed = 1, playing = false, remainder = 0, last = 0, scheduled = null;
    const snapshot = () => ({hour, speed, playing, duration});
    const visualSnapshot = () => ({...snapshot(), fraction:remainder});
    const emit = () => { onChange(snapshot()); onFrame(visualSnapshot()); };
    function stop() {
        playing = false;
        if (scheduled !== null) cancel(scheduled);
        scheduled = null;
    }
    function advance(timestamp) {
        remainder += Math.max(0, timestamp - last) * speed / 1000;
        last = timestamp;
        const steps = Math.floor(remainder + 1e-9);
        if (steps) {
            hour = Math.min(duration, hour + steps);
            remainder = Math.max(0, remainder - steps);
            if (hour === duration) { stop(); remainder = 0; }
        }
        return steps > 0;
    }
    function tick(timestamp) {
        scheduled = null;
        if (!playing) return;
        if (advance(timestamp)) emit();
        else onFrame(visualSnapshot());
        if (playing) scheduled = request(tick);
    }
    return {
        snapshot, visualSnapshot,
        play() {
            if (playing || !duration) return;
            if (hour === duration) { hour = 0; remainder = 0; }
            playing = true; last = now(); scheduled = request(tick); emit();
        },
        pause() {
            if (playing) advance(now());
            stop(); emit();
        },
        seek(value) {
            stop(); hour = Math.max(0, Math.min(duration, Math.round(value)));
            remainder = 0; emit();
        },
        step(delta) { this.seek(hour + delta); },
        setSpeed(value) {
            if (![0.25, 0.5, 1, 2, 4, 8].includes(value)) return;
            if (playing) advance(now());
            speed = value; emit();
        },
        reset(nextDuration = duration) {
            stop(); duration = nextDuration; hour = 0; remainder = 0; emit();
        },
        destroy: stop,
    };
}

function frameAt(result, elapsed, name) {
    const p = result.plant, rows = result.records[name];
    const hour = Math.max(0, Math.min(rows.length, Math.round(elapsed)));
    const row = hour ? rows[hour - 1] : {
        pv_kw: 0, electrical_demand_kw: 0, productive_kw: 0, charge_kw: 0,
        discharge_kw: 0, curtailed_kw: 0, h2_kg: 0, started: 0, on: 0,
        battery_kwh: p.battery_kwh * p.initial_soc, capacity_kw: p.electrolyser_kw,
        controller_status: 'ready',
    };
    const completed = rows.slice(0, hour);
    return {...row, hour, hydrogen_kg: completed.reduce((sum, r) => sum + r.h2_kg, 0),
        starts: completed.reduce((sum, r) => sum + r.started, 0),
        soc: p.battery_kwh ? 100 * row.battery_kwh / p.battery_kwh : 0,
        load: 100 * row.productive_kw / p.electrolyser_kw};
}

function mountPlayback(element, props, watch) {
    let result = props.value, controller = 'Forecast MPC';
    const root = element.querySelector('.console');
    const $ = selector => element.querySelector(selector);
    const text = (key, value) => element.querySelectorAll(`[data-field="${key}"]`)
        .forEach(node => { node.textContent = value; });
    const fmt = (n, digits = 0) => n.toLocaleString('en-GB', {
        minimumFractionDigits: digits, maximumFractionDigits: digits});
    const pad = (n, width = 2) => String(n).padStart(width, '0');
    const stamp = hour => `D${pad(Math.floor(hour / 24) + 1)} / ${pad(hour % 24)}:00`;
    const meter = (name, value) => {
        $(`[data-meter="${name}"]`).style.width = `${Math.max(0, Math.min(100, value))}%`;
    };
    initialisePlantScene(element);
    const inspector = createPlantInspector(element);

    function traces(hour) {
        const n = result.records.Greedy.length, p = result.plant;
        const chartWidth = Math.max(280, $('[data-role="traces"]').clientWidth);
        $('[data-role="traces"]').setAttribute('viewBox', `0 0 ${chartWidth} 275`);
        const left = 88, right = chartWidth - 14, width = right - left;
        const x = h => left + h / n * width;
        const chart = [
            {label: 'LOAD / kW', max: Math.max(1, p.electrolyser_kw + p.start_energy_kwh),
                values: rows => rows.map(r => r.electrical_demand_kw), hourly: true},
            {label: 'SOC / kWh', max: Math.max(1, p.battery_kwh),
                values: rows => [p.battery_kwh * p.initial_soc, ...rows.map(r => r.battery_kwh)]},
            {label: 'H₂ / kg', max: Math.max(1, ...Object.values(result.metrics).map(m => m.hydrogen_kg)),
                values: rows => { let sum = 0; return [0, ...rows.map(r => (sum += r.h2_kg))]; }},
        ];
        let markup = '';
        chart.forEach((c, index) => {
            const top = 10 + index * 83, bottom = top + 57;
            const y = value => bottom - value / c.max * 47;
            markup += `<text x="0" y="${top + 13}" fill="#b5a184" font-size="11">${c.label}</text><text x="0" y="${top + 31}" fill="#b5a184" font-size="11">${fmt(c.max, c.max < 10 ? 1 : 0)}</text>`;
            for (let h = 0; h <= n; h += 24) {
                markup += `<path d="M${x(h)} ${top}V${bottom}" stroke="#403729"/>`;
            }
            markup += `<path d="M${left} ${bottom}H${right}" stroke="#685032"/>`;
            const s = result.scenario;
            if (s.fault_capacity_fraction < 1 && s.fault_duration_hours > 0 && hour > s.fault_start_hour) {
                const end = Math.min(hour, s.fault_start_hour + s.fault_duration_hours);
                markup += `<rect x="${x(s.fault_start_hour)}" y="${top}" width="${x(end) - x(s.fault_start_hour)}" height="57" fill="#ffa32d" opacity=".12"/>`;
            }
            for (const [name, color, dash] of [['Greedy', '#ddd1bc', '4 4'], ['Forecast MPC', '#ffa32d', '']]) {
                const values = c.values(result.records[name].slice(0, hour));
                let path = '';
                if (c.hourly) {
                    values.forEach((v, i) => { path += `${i ? 'L' : 'M'}${x(i)},${y(v)}H${x(i + 1)}`; });
                } else {
                    path = values.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join('');
                }
                if (path) markup += `<path d="${path}" fill="none" stroke="${color}" stroke-width="1.8" stroke-dasharray="${dash}"/>`;
            }
            markup += `<path d="M${x(hour)} ${top}V${bottom}" stroke="#ffa32d" stroke-dasharray="2 3"/>`;
        });
        for (let h = 0; h <= n; h += n > 120 ? 48 : 24) {
            markup += `<text x="${x(h)}" y="269" text-anchor="${h === n ? 'end' : 'middle'}" fill="#b5a184" font-size="11">${h}h</text>`;
        }
        $('[data-role="traces"]').innerHTML = markup;
    }

    function render(state) {
        const {hour, duration, playing, speed} = state;
        const p = result.plant, f = frameAt(result, hour, controller);
        text('play-status', playing ? 'PLAYING' : hour === duration ? 'COMPLETE' : 'PAUSED');
        text('sim-time', stamp(hour)); text('hour-count', `HOUR ${pad(hour, 3)} / ${pad(duration, 3)}`);
        text('interval', hour ? `${fmt(100 * hour / duration)}% COMPLETE` : 'INITIAL INVENTORY');
        text('speed-note', `${speed}× = ${speed} simulated ${speed === 1 ? 'hour' : 'hours'} / second`);
        const play = $('[data-action="play"]');
        play.textContent = playing ? 'Ⅱ PAUSE' : hour === duration ? '↺ REPLAY' : '▶ PLAY';
        play.setAttribute('aria-label', playing ? 'Pause simulation' : hour === duration ? 'Replay simulation' : 'Play simulation');
        $('[data-action="back"]').disabled = hour === 0;
        $('[data-action="next"]').disabled = hour === duration;
        element.querySelectorAll('[data-speed]').forEach(b => b.setAttribute('aria-pressed', Number(b.dataset.speed) === speed));
        element.querySelectorAll('[data-controller]').forEach(b => b.setAttribute('aria-pressed', b.dataset.controller === controller));
        const scrubber = $('[data-role="scrubber"]');
        scrubber.max = duration; scrubber.value = hour;
        scrubber.setAttribute('aria-valuetext', `Hour ${hour} of ${duration}, ${stamp(hour)}`);
        scrubber.style.background = `linear-gradient(to right,#ffa32d ${hour / duration * 100}%,#56432c ${hour / duration * 100}%)`;
        text('solar', fmt(f.pv_kw)); text('solar-cap', `${fmt(p.solar_kw)} kW`);
        text('solar-status', !hour ? 'AWAITING FIRST STEP' : f.pv_kw > .01 ? 'SOLAR / AVAILABLE' : 'NIGHT / NO SOLAR');
        for (const [label, key] of [['demand','electrical_demand_kw'],['charge','charge_kw'],['discharge','discharge_kw'],['curtailed','curtailed_kw'],['productive','productive_kw']]) text(label, fmt(f[key]));
        meter('solar', p.solar_kw ? f.pv_kw / p.solar_kw * 100 : 0); meter('battery', f.soc);
        text('soc', p.battery_kwh ? fmt(f.soc) : '—');
        text('stored', `${fmt(f.battery_kwh)} / ${fmt(p.battery_kwh)} kWh`);
        text('battery-status', !p.battery_kwh ? 'ABSENT' : f.charge_kw > .01 ? 'CHG' : f.discharge_kw > .01 ? 'DIS' : 'IDLE');
        text('h2', fmt(f.hydrogen_kg, 1)); text('h2-rate', fmt(f.h2_kg, 1)); text('starts', pad(f.starts));
        text('load', `${fmt(f.load)}%`); text('plant-status', f.started ? 'STARTING' : f.on ? 'PRODUCING' : 'STANDBY');
        text('capacity', `CAPACITY ${fmt(f.capacity_kw)} / ${fmt(p.electrolyser_kw)} kW`);
        text('fault-status', f.capacity_kw < p.electrolyser_kw ? `FAULT / ${fmt(100 * (1 - f.capacity_kw / p.electrolyser_kw))}% LOSS` : 'CAPACITY / NOMINAL');
        text('readout-period', hour ? `${stamp(hour - 1)} → ${pad(hour % 24)}:00` : 'INITIAL STATE');
        text('solver', !hour ? 'CONTROLLER READY' : `${controller === 'Greedy' ? 'RULE' : 'SOLVER'} / ${f.controller_status.toUpperCase()}`);
        updatePlantScene(element, p, f, state);
        inspector.render({result, frame:f, state, controller, economics:props.economics});
        if ($('[data-role="live-analysis"]').open) traces(hour);
        $('[data-role="comparison"]').innerHTML = `<table aria-label="Controller comparison through hour ${hour}"><thead><tr><th>THROUGH HOUR ${pad(hour, 3)}</th><th>H₂ / kg</th><th>BATTERY / kWh</th><th>STARTS</th></tr></thead><tbody>${['Forecast MPC','Greedy'].map(name => {
            const item = frameAt(result, hour, name);
            return `<tr class="${name === 'Greedy' ? 'greedy' : ''}"><td>${name.toUpperCase()}</td><td>${fmt(item.hydrogen_kg, 1)}</td><td>${fmt(item.battery_kwh, 1)}</td><td>${item.starts}</td></tr>`;
        }).join('')}</tbody></table>`;
    }
    const clock = createPlaybackClock({duration: result.records.Greedy.length, onChange: render});
    function initialise() {
        result = props.value;
        const duration = result.records.Greedy.length;
        text('weather', `${result.scenario.weather.toUpperCase()} / SEED ${result.scenario.seed}`);
        $('[data-role="day-labels"]').innerHTML = Array.from({length: result.scenario.days + 1}, (_, d) =>
            `<span>${d === result.scenario.days ? 'END' : `D${pad(d + 1)}`}</span>`).join('');
        clock.reset(duration);
    }
    element.addEventListener('click', event => {
        const button = event.target.closest('button');
        if (!button || !element.contains(button) || button.disabled) return;
        if (button.dataset.speed) clock.setSpeed(Number(button.dataset.speed));
        if (button.dataset.controller) { controller = button.dataset.controller; render(clock.snapshot()); }
        switch (button.dataset.action) {
            case 'play': clock.snapshot().playing ? clock.pause() : clock.play(); break;
            case 'reset': clock.seek(0); break;
            case 'back': clock.step(-1); break;
            case 'next': clock.step(1); break;
        }
    });
    element.addEventListener('input', event => {
        if (event.target.matches('[data-role="scrubber"]')) clock.seek(Number(event.target.value));
    });
    root.addEventListener('keydown', event => {
        if (event.target.closest('.scene-scroll') || event.target.closest('input,select,textarea,button,summary,[role=button]') || event.ctrlKey || event.metaKey || event.altKey) return;
        if (event.code === 'Space') { event.preventDefault(); clock.snapshot().playing ? clock.pause() : clock.play(); }
        else if (event.code === 'ArrowLeft') { event.preventDefault(); clock.step(-1); }
        else if (event.code === 'ArrowRight') { event.preventDefault(); clock.step(1); }
        else if (event.code === 'Home' || event.code === 'KeyR') { event.preventDefault(); clock.seek(0); }
        else if (event.code === 'End') { event.preventDefault(); clock.seek(clock.snapshot().duration); }
    });
    const hide = () => { if (document.hidden && clock.snapshot().playing) clock.pause(); };
    document.addEventListener('visibilitychange', hide);
    // Pause on leaving the operation tab; release the clock and document listener on unmount.
    const observer = new MutationObserver(() => {
        if (!element.isConnected) {
            clock.destroy(); document.removeEventListener('visibilitychange', hide);
            observer.disconnect(); resizeObserver.disconnect();
        } else if (!root.getClientRects().length && clock.snapshot().playing) clock.pause();
    });
    observer.observe(document.body, {childList:true, subtree:true, attributes:true, attributeFilter:['hidden','style','class']});
    let lastWidth = 0;
    const resizeObserver = new ResizeObserver(() => {
        const width = root.clientWidth;
        if (width > 0 && width !== lastWidth) {
            lastWidth = width; traces(clock.snapshot().hour);
        }
    });
    resizeObserver.observe(root);
    $('[data-role="live-analysis"]').addEventListener('toggle', () => { if ($('[data-role="live-analysis"]').open) traces(clock.snapshot().hour); });
    watch('economics', () => render(clock.snapshot()));
    watch('value', initialise);
    initialise();
}

if (typeof module !== 'undefined' && module.exports) module.exports = {createPlaybackClock, frameAt};
