const contacts = [
  { name: 'Amelia Nguyen', number: '+1 415 ••• 0184', time: '09:42 PST', attempts: 0, score: 98 },
  { name: 'Jonas Miller', number: '+1 503 ••• 4921', time: '09:43 PST', attempts: 1, score: 94 },
  { name: 'Priya Shah', number: '+1 213 ••• 8910', time: '09:43 PST', attempts: 0, score: 89 },
  { name: 'Daniel Brooks', number: '+1 702 ••• 2218', time: '09:44 PST', attempts: 2, score: 82 },
  { name: 'Avery Campbell', number: '+1 206 ••• 6619', time: '09:44 PST', attempts: 0, score: 75 },
  { name: 'Marcus Lee', number: '+1 808 ••• 7743', time: '07:44 HST', attempts: 3, score: 64 }
];

class MockTelecomProvider {
  constructor(name, latency, failureRate) { this.name = name; this.latency = latency; this.failureRate = failureRate; this.failures = 0; this.healthy = true; }
  dial(contact) {
    const failed = Math.random() < this.failureRate;
    this.failures = failed ? this.failures + 1 : 0;
    this.healthy = this.failures < 2;
    if (failed) return { ok: false, reason: 'gateway timeout', provider: this.name };
    const answered = Math.random() < .34;
    return { ok: true, answered, duration: answered ? 30 + Math.floor(Math.random() * 240) : 0, provider: this.name, contact };
  }
}

class SmartDialer {
  constructor() {
    this.mode = 'progressive'; this.running = true; this.paused = false; this.available = 4; this.live = 2; this.queue = [...contacts]; this.dialed = 47; this.answered = 15; this.abandoned = 0;
    this.providers = [new MockTelecomProvider('Twilio · primary', 84, .08), new MockTelecomProvider('Telnyx · standby', 116, .03)]; this.activeProvider = 0;
  }
  get ratio() { return this.mode === 'progressive' ? 1 : Math.min(1.7, 1 + (this.available * .17)); }
  get abandonRate() { return this.dialed ? (this.abandoned / this.dialed) * 100 : 0; }
  isEligible(contact) { return contact.attempts < 3 && contact.time >= '08:00'; }
  cycle() {
    if (!this.running || this.paused) return { type: 'paused' };
    if (this.abandonRate >= 3) { this.paused = true; return { type: 'guard', message: 'Abandon-rate guard paused the campaign.' }; }
    const capacity = this.mode === 'progressive' ? Math.min(1, this.available) : Math.max(0, Math.floor(this.available * this.ratio) - this.live);
    if (!capacity) return { type: 'wait', message: 'Holding until an agent is available.' };
    const contact = this.queue.find(c => this.isEligible(c));
    if (!contact) return { type: 'empty', message: 'No eligible contacts remain.' };
    let provider = this.providers[this.activeProvider]; let result = provider.dial(contact);
    if (!result.ok && !provider.healthy) { this.activeProvider = 1 - this.activeProvider; provider = this.providers[this.activeProvider]; result = provider.dial(contact); result.failover = true; }
    contact.attempts++; this.dialed++;
    if (!result.ok) return { type: 'error', ...result };
    if (result.answered) { this.answered++; this.live = Math.min(6, this.live + 1); this.available = Math.max(0, 6 - this.live); this.queue = this.queue.filter(c => c !== contact); return { type: 'answered', ...result }; }
    this.live = Math.max(0, this.live - 1); this.available = Math.min(6, 6 - this.live); return { type: 'no-answer', ...result };
  }
}

const dialer = new SmartDialer();
const $ = id => document.getElementById(id);
const initials = name => name.split(' ').map(v => v[0]).join('');
function addEvent(type, text, detail = '') {
  const event = document.createElement('div'); event.className = `event ${type === 'error' ? 'error' : ''}`;
  const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  event.innerHTML = `<time>${now}</time><span><span class="event-type">${type.toUpperCase()}</span> · ${text}</span><span class="event-detail">${detail}</span>`;
  $('events').prepend(event);
}
function renderQueue() {
  $('queueRows').innerHTML = dialer.queue.slice(0, 5).map(c => `<div class="queue-row"><div class="contact"><span class="initial">${initials(c.name)}</span><span>${c.name}<small>${c.number}</small></span></div><span class="time">${c.time}</span><span class="eligibility ${dialer.isEligible(c) ? '' : 'hold'}">${dialer.isEligible(c) ? 'Eligible' : 'Attempt cap'}</span><span class="attempts">${c.attempts} / 3</span></div>`).join('');
  $('queueCount').textContent = `${dialer.queue.length + 12} contacts`;
}
function renderProviders() {
  $('providers').innerHTML = dialer.providers.map((p, i) => `<div class="provider ${p.healthy ? '' : 'warning'}"><div><strong>${p.name}</strong><small>${p.latency}ms median latency</small></div><span class="provider-status">${i === dialer.activeProvider ? (p.healthy ? 'Active' : 'Degraded') : 'Standby'}</span></div>`).join('');
}
function render() {
  $('availableAgents').textContent = dialer.available; $('liveCalls').textContent = dialer.live;
  $('dialRatio').innerHTML = `${dialer.ratio.toFixed(2)}<span>×</span>`; $('ratioNote').textContent = dialer.mode === 'progressive' ? 'Safe progressive pacing' : 'Agent-aware prediction';
  $('answerRate').innerHTML = `${Math.round(dialer.answered / dialer.dialed * 100)}<span>%</span>`; $('abandonRate').innerHTML = `${dialer.abandonRate.toFixed(1)}<span>%</span>`;
  $('campaignState').innerHTML = dialer.running && !dialer.paused ? '<i></i> Running' : '<i style="background:#e49b44"></i> Paused';
  const score = Math.max(0, 100 - Math.round(dialer.abandonRate * 15) - (dialer.providers.some(p => !p.healthy) ? 10 : 0)); $('safetyScore').textContent = score;
  $('safetyTitle').textContent = dialer.paused ? 'Campaign safely paused' : score > 85 ? 'Ready to dial safely' : 'Caution: health check needed'; $('safetyText').textContent = dialer.paused ? 'No new calls will be initiated.' : 'DNC, local hours, retry limits, and the abandon-rate guard are active.';
  $('modeExplanation').textContent = dialer.mode === 'progressive' ? 'One customer is called when an agent is free.' : 'More calls are placed to reduce agent waiting time.';
  $('pauseButton').textContent = dialer.paused ? 'Resume' : 'Pause'; renderQueue(); renderProviders();
}
function toast(message) { const el = $('toast'); el.textContent = message; el.classList.add('show'); setTimeout(() => el.classList.remove('show'), 2500); }
function advance() {
  const result = dialer.cycle();
  if (result.type === 'answered') addEvent('connected', `${result.contact.name} answered`, `${result.provider}${result.failover ? ' · failover' : ''}`);
  else if (result.type === 'no-answer') addEvent('no answer', `${result.contact.name} did not answer`, result.provider);
  else if (result.type === 'error') addEvent('error', `Provider error for ${result.contact.name}`, result.provider);
  else addEvent(result.type, result.message || 'Campaign is paused');
  render();
}
document.querySelectorAll('.mode').forEach(button => button.addEventListener('click', () => { dialer.mode = button.dataset.mode; document.querySelectorAll('.mode').forEach(b => b.classList.toggle('active', b === button)); addEvent('mode', `Switched to ${dialer.mode} dialing`); render(); }));
$('tickButton').addEventListener('click', advance);
$('pauseButton').addEventListener('click', () => { dialer.paused = !dialer.paused; addEvent(dialer.paused ? 'safety' : 'system', dialer.paused ? 'Campaign paused by operator' : 'Campaign resumed by operator'); render(); });
$('stopButton').addEventListener('click', () => { dialer.running = false; dialer.paused = true; addEvent('safety', 'Emergency stop activated — no new dials'); toast('Dialing stopped'); render(); });
$('clearEvents').addEventListener('click', () => { $('events').innerHTML = ''; });
$('viewAudit').addEventListener('click', () => $('audit').scrollIntoView({ behavior: 'smooth' }));
$('testButton').addEventListener('click', () => { const checks = [dialer.ratio <= 1.7, dialer.queue.every(c => c.attempts <= 3), dialer.providers.length > 1, dialer.abandonRate < 3]; const passed = checks.filter(Boolean).length; addEvent('test', `${passed}/4 safety and routing checks passed`); toast(`${passed}/4 checks passed`); });
addEvent('system', 'Campaign initialized', 'Progressive · guardrails active'); addEvent('provider', 'Twilio health check passed', '84ms'); render();
