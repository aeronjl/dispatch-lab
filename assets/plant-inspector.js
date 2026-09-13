/* Context stays attached to equipment; every financial state is calculated by Python. */
function componentInspection(part, p, f, c, capital, assumptions) {
    const fmt = (n, d = 1) => n.toLocaleString('en-GB', {maximumFractionDigits:d});
    const eur = n => n == null ? '—' : `€${fmt(n, 2)}`;
    const bucket = name => c?.buckets_eur[name] ?? 0;
    const assets = capital?.assets ?? {};
    const cost = (label, n) => [label, c ? eur(n) : 'UPDATING', 'cost'];
    const specs = {
        solar: {
            title:'Solar array', tag:'GENERATION / OWNERSHIP',
            facts:[['Output this interval', `${fmt(f.pv_kw)} kW`], ['Installed capacity', `${fmt(p.solar_kw)} kW`],
                cost('Ownership so far', bucket('Solar ownership')), cost('Upfront solar', assets.Solar)],
            insight:'More solar can feed the stack and refill storage, but excess is unused when the stack or battery cannot accept it. Ownership cost accrues even at night.',
        },
        battery: {
            title:'Battery storage', tag:'TIME SHIFT / CAPITAL USE',
            facts:[['Stored energy', `${fmt(f.battery_kwh)} / ${fmt(p.battery_kwh)} kWh`], ['Power limit', `${fmt(p.battery_kwh * p.battery_c_rate)} kW`],
                cost('Capital use so far', bucket('Battery capital use')), cost('Upfront cells + electronics', (assets['Battery cells'] ?? 0) + (assets['Battery power electronics'] ?? 0))],
            insight:!p.battery_kwh ? 'No battery is installed. Solar must be used immediately or left unharvested.' : `Storage shifts solar into later production. ${c ? fmt(c.battery_loss_kwh) : '—'} kWh has been lost in storage so far. More capacity adds cost; it also increases power at the same C-rate.`,
            wear:c ? `Cells: ${eur(c.allowances.battery_calendar_eur)} calendar vs ${eur(c.allowances.battery_usage_eur)} usage. The larger is allocated once. ${fmt(c.battery_equivalent_cycles, 3)} equivalent cycles so far.` : '',
            report:'Battery sizing',
        },
        stack: {
            title:'Electrolyser', tag:'PRODUCTION / STARTS & WEAR',
            facts:[['Productive power', `${fmt(f.productive_kw)} / ${fmt(f.capacity_kw)} kW`], ['Starts / start energy so far', `${f.starts} / ${c ? fmt(c.startup_kwh) : '—'} kWh`],
                cost('Capital use so far', bucket('Electrolyser capital use')), cost('Fault budget so far', bucket('Fault budget'))],
            insight:`Each start consumes ${fmt(p.start_energy_kwh)} kWh before productive energy becomes hydrogen. Staying on can save starts, but may draw down energy needed later.${f.capacity_kw < p.electrolyser_kw ? ' A fault is limiting capacity in this interval.' : ''}`,
            wear:c ? `Stack: ${eur(c.allowances.stack_calendar_eur)} calendar vs ${eur(c.allowances.stack_usage_eur)} usage; the larger is allocated once. Extra wear per start: ${fmt(assumptions.start_equivalent_hours)} equivalent hours. Incident budgets are allocated when a fault begins, not a repair payment schedule.` : '',
        },
        hydrogen: {
            title:'Hydrogen output', tag:'YIELD / COST PER KILOGRAM',
            facts:[['Produced so far', `${fmt(f.hydrogen_kg)} kg`], ['This interval', `${fmt(f.h2_kg)} kg`],
                ['Allocated cost / kg so far', c ? c.period_eur_per_kg == null ? '— / NO OUTPUT YET' : `${eur(c.period_eur_per_kg)} / kg` : 'UPDATING', 'cost'],
                cost('Water + consumables so far', bucket('Water & consumables'))],
            insight:'Cost per kilogram combines every allocated plant cost with hydrogen actually produced through this hour. It can rise during downtime and fall as production catches up. It is a period measure, not lifetime LCOH.',
            wear:c ? `${fmt(c.water_m3 * 1000)} litres of water allocated to production. Remaining battery inventory is unvalued; check it before comparing controller output.` : '',
        },
        curtailment: {
            title:'Unused solar', tag:'LOST OPPORTUNITY / NO EXTRA CHARGE',
            facts:[['Unused this interval', `${fmt(f.curtailed_kw)} kW`], ['Unused so far', c ? `${fmt(c.curtailed_kwh)} kWh` : '—'],
                ['Additional energy charge', '€0', 'cost']],
            insight:'This is solar the plant could not use or store. It reduces the output obtained from equipment you already own. Adding another electricity charge would count the same solar twice. More storage or stack capacity may recover some of it, at additional capital cost.',
            report:'Battery sizing',
        },
        shared: {
            title:'Shared plant costs', tag:'SITE / INSTALLATION & OPERATION',
            facts:[cost('Site + installation so far', bucket('Installation & site ownership')),
                cost('Standing operation so far', bucket('Standing operation')),
                cost('Total allocated so far', c?.allocated_cost_eur), cost('Whole plant upfront', capital?.upfront_eur)],
            insight:'These costs support the whole plant and accrue with elapsed time, including idle hours. Upfront investment is shown separately from period allocation; the purchase bill is not added a second time.',
            report:'Breakdown',
        },
    };
    return specs[part];
}

function createPlantInspector(element) {
    let selected = null, costsVisible = true, context = null;
    const $ = s => element.querySelector(s);
    const root = $('.console'), drawer = $('[data-role="inspector"]');
    const euro = n => n == null ? '—' : `€${n.toLocaleString('en-GB', {minimumFractionDigits:2,maximumFractionDigits:2})}`;
    const setText = (key, value) => element.querySelectorAll(`[data-cost-field="${key}"]`).forEach(n => {n.textContent = value;});
    function render(next) {
        if (next) context = next;
        if (!context) return;
        const {result, frame:f, state, controller, economics} = context;
        const c = economics?.physical_run_id === result.run_id ? economics.controllers[controller]?.[state.hour] : null;
        const p = result.plant;
        root.dataset.costs = costsVisible;
        const toggle = $('[data-action="costs"]');
        toggle.setAttribute('aria-pressed', costsVisible);
        toggle.textContent = costsVisible ? '▣ COSTS ON' : '□ COSTS OFF';
        setText('period', `THROUGH HOUR ${String(state.hour).padStart(3,'0')}`);
        setText('total', c ? euro(c.allocated_cost_eur) : 'UPDATING');
        setText('unit', c ? c.period_eur_per_kg == null ? '— / NO H₂ YET' : `${euro(c.period_eur_per_kg)} / kg` : 'UPDATING');
        for (const [part, bucket] of [['solar','Solar ownership'],['battery','Battery capital use'],['stack','Electrolyser capital use']]) {
            setText(part, c ? `${euro(c.buckets_eur[bucket])} ALLOCATED` : 'UPDATING COSTS');
        }
        setText('hydrogen', c ? c.period_eur_per_kg == null ? '— €/kg / NO OUTPUT' : `${euro(c.period_eur_per_kg)} / kg SO FAR` : 'UPDATING COSTS');
        setText('fault', c?.buckets_eur['Fault budget'] ? `+ ${euro(c.buckets_eur['Fault budget'])} INCIDENT` : '');
        setText('shared', c ? `${euro(c.buckets_eur['Installation & site ownership'] + c.buckets_eur['Standing operation'])} SHARED COSTS` : 'UPDATING COSTS');
        element.querySelectorAll('[data-inspect]').forEach(n => {
            n.dataset.selected = n.dataset.inspect === selected;
            n.setAttribute('aria-expanded', n.dataset.inspect === selected);
        });
        $('[data-role="component-picker"]').value = selected ?? "";
        drawer.hidden = !selected;
        $('.scene-story').hidden = !!selected;
        if (!selected) return;
        const spec = componentInspection(selected, p, f, c, economics?.capital, economics?.cost_assumptions);
        $('[data-inspector="title"]').textContent = spec.title;
        $('[data-inspector="tag"]').textContent = `${spec.tag} · HOUR ${state.hour} · ${controller.toUpperCase()}`;
        $('[data-inspector="facts"]').innerHTML = spec.facts.filter(x => costsVisible || x[2] !== 'cost').map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join('');
        const otherName = controller === 'Forecast MPC' ? 'Greedy' : 'Forecast MPC';
        const otherFrame = frameAt(result, state.hour, otherName);
        const otherCost = c ? economics.controllers[otherName][state.hour] : null;
        const num = n => n.toLocaleString('en-GB', {maximumFractionDigits:1});
        const withCost = bucket => costsVisible && otherCost ? ` · ${euro(otherCost.buckets_eur[bucket])} allocated` : '';
        const comparison = {
            solar:'Both controllers receive the same sunlight and own the same solar capacity.',
            battery:`${otherName} at this hour: ${num(otherFrame.battery_kwh)} kWh stored${withCost('Battery capital use')}.`,
            stack:`${otherName} through this hour: ${otherFrame.starts} starts${withCost('Electrolyser capital use')}.`,
            hydrogen:`${otherName} through this hour: ${num(otherFrame.hydrogen_kg)} kg H₂${costsVisible && otherCost ? ` · ${euro(otherCost.period_eur_per_kg)} / kg` : ''}.`,
            curtailment:otherCost ? `${otherName} through this hour: ${num(otherCost.curtailed_kwh)} kWh unused.` : '',
            shared:'Both controller scenarios carry the same site and standing allocation.',
        };
        $('[data-inspector="compare"]').textContent = comparison[selected];
        $('[data-inspector="insight"]').textContent = spec.insight;
        $('[data-inspector="wear"]').textContent = costsVisible ? spec.wear ?? '' : '';
        $('[data-action="study"]').hidden = !spec.report;
        $('[data-action="study"]').textContent = spec.report === 'Battery sizing' ? 'COMPARE BATTERY SIZES ↗' : 'OPEN COST BREAKDOWN ↗';
        $('[data-action="study"]').dataset.report = spec.report ?? '';
    }
    function close() {
        const previous = selected; selected = null; render();
        if (previous) $(`[data-inspect="${previous}"]`)?.focus({preventScroll:true});
    }
    function inspect(part) {
        selected = selected === part ? null : part; render();
        if (selected) requestAnimationFrame(() => {
            const available = window.innerHeight - $('.playback-dock').offsetHeight - 12;
            const overflow = drawer.getBoundingClientRect().bottom - available;
            if (overflow > 0) window.scrollBy({top:overflow, behavior:'smooth'});
        });
    }
    element.addEventListener('click', async event => {
        const component = event.target.closest('[data-inspect]');
        if (component) inspect(component.dataset.inspect);
        const button = event.target.closest('button');
        switch (button?.dataset.action) {
            case 'costs': costsVisible = !costsVisible; render(); break;
            case 'close-inspector': close(); break;
            case 'configure': {
                const tabs = [...document.querySelectorAll('#workspace-tabs [role="tab"][data-tab-id]')];
                tabs.find(t => t.textContent.includes('Experiment setup'))?.click();
                requestAnimationFrame(() => window.scrollTo({top:0,behavior:'instant'}));
                break;
            }
            case 'study': {
                const report = document.querySelector('#cost-report');
                const content = report?.querySelector('[data-testid="accordion-content"]');
                if (content?.style.display === 'none') report.querySelector('button.label-wrap')?.click();
                await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                [...(report?.querySelectorAll('[role="tab"]') ?? [])].find(t => t.textContent.trim() === button.dataset.report)?.click();
                report?.scrollIntoView({behavior:'smooth',block:'start'});
                break;
            }
        }
    });
    $('[data-role="component-picker"]').addEventListener('change', event => {
        selected = event.target.value || null; render();
        const positions = {solar:0, battery:300, stack:540, hydrogen:724, curtailment:0, shared:700};
        $('.scene-scroll').scrollTo({left:positions[selected] ?? 0, behavior:'instant'});
        if (selected) drawer.scrollIntoView({behavior:'smooth',block:'center'});
    });
    element.addEventListener('keydown', event => {
        const target = event.target.closest('[data-inspect]');
        if (target && ['Enter',' '].includes(event.key)) { event.preventDefault(); event.stopPropagation(); inspect(target.dataset.inspect); }
        if (event.key === 'Escape' && selected) { event.preventDefault(); close(); }
    });
    return {render};
}
if (typeof module !== 'undefined' && module.exports) module.exports = {componentInspection};
