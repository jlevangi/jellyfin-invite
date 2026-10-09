const byId = id => document.getElementById(id);
const status = byId('status');
const tokenInput = byId('token');
const login = byId('login'), app = byId('app'), loginStatus = byId('loginStatus');
const unlockBtn = byId('unlockBtn'), refreshBtn = byId('refreshBtn'), lockBtn = byId('lockBtn');
const inviteForm = byId('inviteForm'), note = byId('note'), days = byId('days'), maxUses = byId('maxUses'), createBtn = byId('createBtn');
const listStatus = byId('listStatus'), out = byId('out'), toast = byId('toast');
const activeCount = byId('activeCount'), redemptionCount = byId('redemptionCount'), expiredCount = byId('expiredCount'), revokedCount = byId('revokedCount');
let csrfToken = null;
let authMode = 'password';

function headers(options = {}) {
  const result = {'Content-Type': 'application/json', ...(options.headers || {})};
  if (authMode === 'password') result['X-Admin-Token'] = sessionStorage.inviteToken || tokenInput.value;
  if (authMode === 'cookie' && csrfToken && options.method && options.method !== 'GET') result['X-CSRF-Token'] = csrfToken;
  return result;
}

async function api(url, options = {}) {
  const response = await fetch(url, {...options, headers: headers(options), credentials: 'same-origin'});
  const json = await response.json();
  if (!response.ok || !json.ok) throw Error(json.message || 'Request failed');
  return json;
}

function inviteState(invite) {
  if (invite.revoked_at) return 'revoked';
  if (new Date(invite.expires_at) < new Date()) return 'expired';
  if (invite.use_count >= invite.max_uses) return 'exhausted';
  return 'active';
}

function say(message) {
  toast.textContent = message; toast.classList.remove('hidden');
  setTimeout(() => toast.classList.add('hidden'), 2200);
}

async function copy(value) {
  try { await navigator.clipboard.writeText(value); say('Invite link copied'); }
  catch { say('Copy failed. Select and copy the invite link manually.'); }
}

function button(label, callback, className = 'secondary') {
  const element = document.createElement('button'); element.type = 'button'; element.className = className;
  element.textContent = label; element.addEventListener('click', callback); return element;
}

function render(invite) {
  const status = inviteState(invite), card = document.createElement('article'); card.className = 'invite-card';
  const head = document.createElement('div'); head.className = 'invite-card-head';
  const pill = document.createElement('span'); pill.className = `pill ${status}`; pill.textContent = status;
  const code = document.createElement('code'); code.className = 'invite-code'; code.textContent = invite.code;
  head.append(pill, code); card.append(head);
  const meta = document.createElement('div'); meta.className = 'invite-card-meta';
  const note = document.createElement('span'); note.textContent = invite.note || 'No note';
  const expires = document.createElement('span'); expires.textContent = `Expires ${new Date(invite.expires_at).toLocaleString()}`;
  meta.append(note, expires); card.append(meta);
  const usage = document.createElement('p'); usage.className = 'usage-count'; usage.textContent = `${invite.use_count} of ${invite.max_uses} uses`; card.append(usage);
  if (invite.redemptions.length) {
    const details = document.createElement('details'); details.className = 'redemptions';
    const summary = document.createElement('summary'); summary.textContent = `View ${invite.use_count} redemption${invite.use_count === 1 ? '' : 's'}`;
    const list = document.createElement('ul');
    invite.redemptions.forEach(redemption => { const item = document.createElement('li'); item.textContent = `${redemption.email} — ${new Date(redemption.redeemed_at).toLocaleString()}`; list.append(item); });
    details.append(summary, list); card.append(details);
  }
  const inviteUrl = document.createElement('a'); inviteUrl.className = 'invite-url'; inviteUrl.href = invite.url; inviteUrl.textContent = invite.url;
  inviteUrl.target = '_blank'; inviteUrl.rel = 'noopener noreferrer';
  card.append(inviteUrl);
  const actions = document.createElement('div'); actions.className = 'invite-card-actions';
  actions.append(button('Copy link', () => copy(invite.url), ''));
  if (status === 'active') actions.append(button('Revoke', () => revoke(invite.code), 'secondary danger'));
  card.append(actions); return card;
}

function counts(items) {
  const totals = {active: 0, expired: 0, revoked: 0, redemptions: 0};
  items.forEach(invite => { const current = inviteState(invite); if (current in totals && current !== 'redemptions') totals[current]++; totals.redemptions += invite.use_count; });
  activeCount.textContent = totals.active; redemptionCount.textContent = totals.redemptions;
  expiredCount.textContent = totals.expired; revokedCount.textContent = totals.revoked;
}

function showLogin(message = '') {
  app.classList.add('hidden'); login.classList.remove('hidden'); loginStatus.textContent = message;
  loginStatus.classList.toggle('error', Boolean(message));
}

async function unlock() {
  loginStatus.textContent = 'Signing in…'; loginStatus.classList.remove('error'); unlockBtn.disabled = true; authMode = 'password';
  try {
    sessionStorage.inviteToken = tokenInput.value; await list(); login.classList.add('hidden'); app.classList.remove('hidden'); lockBtn.classList.remove('hidden');
  } catch (error) { sessionStorage.removeItem('inviteToken'); loginStatus.textContent = error.message; loginStatus.classList.add('error'); }
  finally { unlockBtn.disabled = false; }
}

async function logout() {
  lockBtn.disabled = true;
  try { await api('/api/admin/logout', {method: 'POST'}); }
  catch (error) { if (authMode === 'cookie') { loginStatus.textContent = error.message; loginStatus.classList.add('error'); lockBtn.disabled = false; return; } }
  sessionStorage.removeItem('inviteToken'); tokenInput.value = ''; csrfToken = null; authMode = 'password';
  app.classList.add('hidden'); lockBtn.classList.add('hidden'); login.classList.remove('hidden'); loginStatus.textContent = ''; loginStatus.classList.remove('error'); lockBtn.disabled = false;
}

async function list() {
  listStatus.textContent = 'Loading invites…'; listStatus.classList.remove('error'); refreshBtn.disabled = true;
  try {
    const json = await api('/api/admin/invites'); counts(json.invites); out.replaceChildren(...json.invites.map(render));
    if (!json.invites.length) { const empty = document.createElement('p'); empty.className = 'muted empty'; empty.textContent = 'No invites yet. Create one above.'; out.append(empty); }
    listStatus.textContent = `${json.invites.length} invite${json.invites.length === 1 ? '' : 's'}`;
  } catch (error) {
    listStatus.textContent = error.message; listStatus.classList.add('error');
    if (authMode === 'cookie' && /unauthorized|session|admin/i.test(error.message)) { csrfToken = null; showLogin('Your admin session expired. Sign in again.'); }
    throw error;
  } finally { refreshBtn.disabled = false; }
}

async function create(event) {
  event.preventDefault(); status.textContent = 'Creating invite…'; status.classList.remove('error'); createBtn.disabled = true;
  try {
    const json = await api('/api/admin/invites', {method: 'POST', body: JSON.stringify({note: note.value, expiresDays: days.value, maxUses: maxUses.value})});
    note.value = ''; status.textContent = 'Invite created.'; await copy(json.url); await list();
  } catch (error) { status.textContent = error.message; status.classList.add('error'); }
  finally { createBtn.disabled = false; }
}

async function revoke(code) {
  if (!confirm('Revoke this invite?')) return;
  try { await api(`/api/admin/invites/${encodeURIComponent(code)}/revoke`, {method: 'POST', body: '{}'}); say('Invite revoked'); await list(); }
  catch (error) { say(error.message); }
}

unlockBtn.addEventListener('click', unlock);
refreshBtn.addEventListener('click', () => list().catch(() => {}));
lockBtn.addEventListener('click', logout);
inviteForm.addEventListener('submit', create);
tokenInput.addEventListener('keydown', event => { if (event.key === 'Enter') unlock(); });

async function initialize() {
  try {
    const session = await fetch('/api/admin/session', {credentials: 'same-origin'}).then(response => response.json());
    if (session.authenticated) {
      authMode = 'cookie'; csrfToken = session.csrfToken; await list(); login.classList.add('hidden'); app.classList.remove('hidden'); lockBtn.classList.remove('hidden'); return;
    }
  } catch { /* Password sign-in remains available if session discovery fails. */ }
  const savedToken = sessionStorage.inviteToken;
  if (savedToken) { tokenInput.value = savedToken; await unlock(); }
}
initialize();
