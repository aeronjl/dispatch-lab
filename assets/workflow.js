/* Navigation is a view of saved work, never a second source of model state. */
function workflowMatches(label, query) {
    const text = label.toLocaleLowerCase();
    return query.trim().toLocaleLowerCase().split(/\s+/).every(term => text.includes(term));
}

function workspaceReturnLabel(origin) {
    if (origin?.closest('.pj-workspace')) return 'Back to project';
    if (origin?.closest('.si-workspace')) return 'Back to site study';
    if (origin?.closest('.st-workspace')) return 'Back to study';
    if (origin?.closest('.iv-workspace')) return 'Back to investigation';
    if (origin?.closest('.x-workspace')) return 'Back to component';
    if (origin?.closest('.s-workspace')) return 'Back to solar';
    if (origin?.closest('.m-inspector')) return 'Back to component';
    return 'Back to simulation';
}

function labelWorkspaceReturn(button, origin) {
    if (!button) return;
    const label = workspaceReturnLabel(origin);
    button.textContent = '← ' + label.replace('Back to ', '');
    button.setAttribute('aria-label', label);
}

// A live progress update may replace the button while a child workspace is open.
// Retain its semantic address as well as its original DOM node.
function rememberWorkspaceFocus(root, origin) {
    const scopes = ['.pj-workspace','.si-workspace','.st-workspace','.iv-workspace','.x-workspace','.s-workspace','.m-inspector','.m-utility'];
    const scope = scopes.find(selector => origin?.closest(selector));
    const attributes = [...(origin?.attributes || [])].filter(a => /^data-(pj|si|st|iv|x|d|do|model-topic|model-context|explore|work|case)(-|$)/.test(a.name));
    const selector = attributes.map(a => `[${a.name}="${CSS.escape(a.value)}"]`).join('');
    const available = node => node?.isConnected && node.getClientRects().length && !node.closest('[hidden],[inert]');
    return () => {
        const replacement = scope && selector ? root.querySelector(scope + ' ' + selector) : null;
        const target = available(origin) ? origin : available(replacement) ? replacement : root.querySelector('[data-do=menu]');
        target?.focus({preventScroll:true});
    };
}

function createWorkflow({root, getResult, getFrame}) {
    const q = s => root.querySelector(s);
    function filter() {
        const term = q('[data-work-search]').value;
        let total = 0;
        root.querySelectorAll('[data-work-group]').forEach(group => {
            let count = 0;
            group.querySelectorAll('button').forEach(button => {
                const unavailable = button.dataset.unavailable === 'true';
                button.hidden = unavailable || !workflowMatches(button.textContent + ' ' + (button.dataset.keywords || ''), term);
                if (!button.hidden) count++;
            });
            group.hidden = !count;
            total += count;
        });
        q('[data-work-empty]').hidden = !!total;
    }
    function sync() {
        const result = getResult(), frame = getFrame();
        q('[data-work-context]').textContent = `Recorded operation · H${frame.hour} · ${frame.controller}`;
        q('.wf-offline').hidden = !result.offline_mode;
        for (const selector of ['[data-do=project]', '[data-work=build]', '[data-work=operate]', '[data-work=notes]', '[data-work=reports]', '[data-work=designs]', '[data-work=protocols]', '[data-work=alternative]']) {
            q(selector).disabled = !!result.offline_mode;
        }
        root.querySelectorAll('.m-utility-links [data-do]').forEach(button => {
            button.dataset.unavailable = String(!!result.offline_mode);
        });
        filter();
    }
    q('[data-work-search]').addEventListener('input', filter);
    return {sync, filter};
}
if (typeof module !== 'undefined') module.exports = {workflowMatches, workspaceReturnLabel};
