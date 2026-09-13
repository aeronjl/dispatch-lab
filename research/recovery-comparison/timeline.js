/* Rendering only: all values come from the two sealed recorded timelines. */
(() => {
  const source = JSON.parse(document.getElementById('data').textContent).window_trace;
  const select = document.getElementById('trace-window');
  const slider = document.getElementById('trace-hour');
  const plot = document.getElementById('trace-plot');
  source.cases.forEach((item, i) => {
    const option = document.createElement('option');
    option.value = i; option.textContent = item.label; select.append(option);
  });
  const fmt = x => Number(x).toFixed(1);
  function render() {
    const record = source.cases[Number(select.value)];
    const rows = record.rows, hour = Number(slider.value), selected = rows[hour];
    const left = 60, right = 910, width = right - left, end = rows.length;
    const x = h => left + width * h / end;
    const panels = [
      {label: 'Interval power / kW', top: 30, height: 110,
       max: Math.ceil(Math.max(1, ...rows.flatMap(r => [r.pv_kw, r.requested_kw, r.delivered_kw])) / 100) * 100,
       series: [['pv_kw', '#887a64', ''], ['requested_kw', '#ffe2b8', '5 5'], ['delivered_kw', '#ffad43', '']]},
      {label: 'Capacity / kW', top: 205, height: 100,
       max: Math.ceil(Math.max(1, ...rows.flatMap(r => [r.true_capacity_kw, r.estimated_capacity_kw])) / 100) * 100,
       series: [['true_capacity_kw', '#887a64', '5 5'], ['estimated_capacity_kw', '#ffad43', '']]}
    ];
    let svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 950 345" role="img" aria-labelledby="trace-title trace-description" style="width:100%;height:auto;display:block"><title id="trace-title">Saved recovery timeline</title><desc id="trace-description">Two plots compare electrical availability and requested versus delivered load, then decision-start estimated capacity versus retrospective physical capacity. The selected interval has an exact text readout below.</desc>';
    for (const panel of panels) {
      const y = v => panel.top + panel.height * (1 - v / panel.max);
      svg += `<text x="${left}" y="${panel.top-12}" fill="#c18c49" font-size="12">${panel.label}</text>`;
      [0, panel.max / 2, panel.max].forEach(value => {
        svg += `<path d="M${left} ${y(value)}H${right}" stroke="#493c2a"/><text x="${left-9}" y="${y(value)+4}" fill="#c18c49" text-anchor="end" font-size="11">${value}</text>`;
      });
      panel.series.forEach(([field, colour, dash]) => {
        // Piecewise-constant hourly values; never interpolate additional physics.
        const points = rows.flatMap(r => [`${x(r.hour)},${y(r[field])}`, `${x(r.hour+1)},${y(r[field])}`]);
        svg += `<polyline points="${points.join(' ')}" fill="none" stroke="${colour}" stroke-width="2" stroke-dasharray="${dash}"/>`;
      });
      svg += `<rect x="${x(hour)}" y="${panel.top}" width="${width/end}" height="${panel.height}" fill="#ffad43" opacity=".1"/><path d="M${x(hour)} ${panel.top}V${panel.top+panel.height}" stroke="#ffad43" stroke-width="1"/>`;
      [0, 12, 24, 36, 48].forEach(h => {
        svg += `<text x="${x(h)}" y="${panel.top+panel.height+20}" fill="#c18c49" text-anchor="middle" font-size="11">H${h}</text>`;
      });
    }
    plot.innerHTML = svg + '</svg>';
    document.getElementById('trace-hour-label').textContent = `H${hour}–${hour+1}`;
    document.getElementById('trace-values').textContent = `${record.label}, H${hour}: ${selected.status}. Available PV ${fmt(selected.pv_kw)} kW; requested load ${fmt(selected.requested_kw)} kW; delivered load ${fmt(selected.delivered_kw)} kW. Estimated capacity ${fmt(selected.estimated_capacity_kw)} kW; retrospective physical capacity ${fmt(selected.true_capacity_kw)} kW. Methane this interval ${fmt(selected.methane_kg)} kg; ending battery ${fmt(selected.ending_battery_kwh)} kWh. Load probe ${selected.probe ? 'requested' : 'not requested'}.`;
  }
  select.addEventListener('change', render); slider.addEventListener('input', render); render();
})();
