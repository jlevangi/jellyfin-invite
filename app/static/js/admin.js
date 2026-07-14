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
  const current = new Date();
  if (invite.revoked_at) return 'revoked';
  if (invite.used_at) return 'used';
  if (new Date(invite.expires_at) < current) return 'expired';
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

function cell(text) {
  const td = document.createElement('td');
  td.textContent = text || '';
  return td;
}

function row(invite) {
  const status = state(invite);
  const url = 'https://join.levangie.dev/j/' + invite.code;
  const tr = document.createElement('tr');

  const statusCell = document.createElement('td');
  const pill = document.createElement('span');
  pill.className = 'pill ' + status;
  pill.textContent = status;
  statusCell.append(pill);
  tr.append(statusCell);

  const linkCell = document.createElement('td');
  const copyButton = document.createElement('button');
  copyButton.className = 'invite-link';
  copyButton.title = 'Click to copy';
  copyButton.textContent = url;
  copyButton.addEventListener('click', () => copy(url));
  linkCell.append(copyButton);
  tr.append(linkCell);

  tr.append(cell(invite.note));
  tr.append(cell(new Date(invite.expires_at).toLocaleString()));
  tr.append(cell(invite.used_by_email));

  const actions = document.createElement('td');
  if (status === 'active') {
    const revokeButton = document.createElement('button');
    revokeButton.className = 'danger';
    revokeButton.textContent = 'Revoke';
    revokeButton.addEventListener('click', () => revoke(invite.code));
    actions.append(revokeButton);
  }
  tr.append(actions);
  return tr;
}

function counts(items) {
  const count = {active: 0, used: 0, expired: 0, revoked: 0};
  items.forEach(invite => count[state(invite)]++);
  activeCount.textContent = count.active;
  usedCount.textContent = count.used;
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
    const td = cell('No invites yet.');
    td.colSpan = 6;
    td.className = 'muted';
    tr.append(td);
    out.append(tr);
  }
}

async function create() {
  try {
    const json = await api('/api/admin/invites', {method: 'POST', body: JSON.stringify({note: note.value, expiresDays: days.value})});
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

if (token.value) unlock();
