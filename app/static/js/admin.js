token.value = sessionStorage.inviteToken || '';

function headers() {
  return {'X-Admin-Token': sessionStorage.inviteToken || token.value, 'Content-Type': 'application/json'};
}

async function api(url, options = {}) {
  const response = await fetch(url, {...options, headers: headers()});
  const json = await response.json();
  if (!response.ok || !json.ok) throw Error(json.message || 'Request failed');
  return json;
}

function state(invite) {
  if (invite.revoked_at) return 'revoked';
  if (new Date(invite.expires_at) < new Date()) return 'expired';
  if (invite.use_count >= invite.max_uses) return 'exhausted';
  return 'active';
}

function say(message) {
  toast.textContent = message;
  toast.classList.remove('hidden');
  setTimeout(() => toast.classList.add('hidden'), 1800);
}

async function copy(value) {
  await navigator.clipboard?.writeText(value);
  say('Invite link copied');
}

function cell(label, content = '') {
  const td = document.createElement('td');
  td.dataset.label = label;
  if (content instanceof Node) td.append(content);
  else td.textContent = content;
  return td;
}

function usage(invite) {
  const wrap = document.createElement('div');
  const count = document.createElement('strong');
  count.className = 'usage-count';
  count.textContent = `${invite.use_count} of ${invite.max_uses} used`;
  wrap.append(count);
  if (invite.redemptions.length) {
    const details = document.createElement('details');
    details.className = 'redemptions';
    const summary = document.createElement('summary');
    summary.textContent = `View ${invite.use_count} redemption${invite.use_count === 1 ? '' : 's'}`;
    const list = document.createElement('ul');
    invite.redemptions.forEach(redemption => {
      const item = document.createElement('li');
      item.textContent = `${redemption.email} — ${new Date(redemption.redeemed_at).toLocaleString()}`;
      list.append(item);
    });
    details.append(summary, list);
    wrap.append(details);
  }
  return wrap;
}

function row(invite) {
  const status = state(invite);
  const url = 'https://join.levangie.dev/j/' + invite.code;
  const tr = document.createElement('tr');

  const pill = document.createElement('span');
  pill.className = 'pill ' + status;
  pill.textContent = status;
  tr.append(cell('Status', pill));

  const copyButton = document.createElement('button');
  copyButton.className = 'invite-link';
  copyButton.title = 'Copy invite link';
  copyButton.textContent = url;
  copyButton.addEventListener('click', () => copy(url));
  tr.append(cell('Invite link', copyButton));

  tr.append(cell('Note', invite.note || '—'));
  tr.append(cell('Expires', new Date(invite.expires_at).toLocaleString()));
  tr.append(cell('Usage', usage(invite)));

  const actions = document.createElement('div');
  actions.className = 'row-actions';
  if (status === 'active') {
    const revokeButton = document.createElement('button');
    revokeButton.className = 'danger';
    revokeButton.textContent = 'Revoke';
    revokeButton.addEventListener('click', () => revoke(invite.code));
    actions.append(revokeButton);
  } else {
    actions.textContent = '—';
  }
  tr.append(cell('Actions', actions));
  return tr;
}

function counts(items) {
  const count = {active: 0, expired: 0, revoked: 0, redemptions: 0};
  items.forEach(invite => {
    const status = state(invite);
    if (status === 'active') count.active++;
    if (status === 'expired') count.expired++;
    if (status === 'revoked') count.revoked++;
    count.redemptions += invite.use_count;
  });
  activeCount.textContent = count.active;
  redemptionCount.textContent = count.redemptions;
  expiredCount.textContent = count.expired;
  revokedCount.textContent = count.revoked;
}

async function unlock() {
  try {
    sessionStorage.inviteToken = token.value;
    await list();
    login.classList.add('hidden');
    app.classList.remove('hidden');
  } catch (error) {
    sessionStorage.removeItem('inviteToken');
    loginStatus.textContent = error.message;
  }
}

function lock() {
  sessionStorage.removeItem('inviteToken');
  token.value = '';
  app.classList.add('hidden');
  login.classList.remove('hidden');
}

async function list() {
  const json = await api('/api/admin/invites');
  counts(json.invites);
  out.replaceChildren(...json.invites.map(row));
  if (!json.invites.length) {
    const tr = document.createElement('tr');
    const td = cell('', 'No invites yet.');
    td.colSpan = 6;
    td.className = 'muted empty';
    tr.append(td);
    out.append(tr);
  }
}

async function create() {
  try {
    const json = await api('/api/admin/invites', {
      method: 'POST',
      body: JSON.stringify({note: note.value, expiresDays: days.value, maxUses: maxUses.value}),
    });
    status.textContent = 'Created ' + json.url;
    await copy(json.url);
    note.value = '';
    await list();
  } catch (error) {
    status.textContent = error.message;
  }
}

async function revoke(code) {
  if (!confirm('Revoke this invite?')) return;
  await api('/api/admin/invites/' + code + '/revoke', {method: 'POST'});
  say('Invite revoked');
  await list();
}

unlockBtn.addEventListener('click', unlock);
refreshBtn.addEventListener('click', list);
lockBtn.addEventListener('click', lock);
createBtn.addEventListener('click', create);
token.addEventListener('keydown', event => { if (event.key === 'Enter') unlock(); });

if (token.value) unlock();
