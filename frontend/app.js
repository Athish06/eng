/**
 * Chummah — app.js
 * Core: streaming display, voice I/O, corrections, sessions.
 */

const API = window.location.origin;

const state = {
    sessionId: null,
    mode: 'casual',
    sessions: [],
    streaming: false,
    recording: false,
    tts: true,
    recognition: null,
    abort: null,
};

// DOM
const $ = id => document.getElementById(id);
const sidebar = $('sidebar');
const sessionsList = $('sessionsList');
const welcomeScreen = $('welcomeScreen');
const messagesArea = $('messagesArea');
const chatContainer = $('chatContainer');
const messageInput = $('messageInput');
const sendBtn = $('sendBtn');
const stopBtn = $('stopBtn');
const micBtn = $('micBtn');
const ttsToggle = $('ttsToggle');
const ttsLabel = $('ttsLabel');
const statusDot = $('statusDot');
const statusText = $('statusText');
const recordingIndicator = $('recordingIndicator');

// ─── Init ──────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

function initApp() {
    initVoice();
    bindEvents();
    checkHealth();
    loadSessions();
}

function bindEvents() {
    sendBtn.addEventListener('click', send);
    stopBtn.addEventListener('click', () => state.abort?.abort());
    micBtn.addEventListener('click', toggleMic);
    $('newChatBtn').addEventListener('click', newChat);
    $('newChatMobile').addEventListener('click', newChat);
    $('hamburgerBtn').addEventListener('click', toggleMobileSidebar);
    $('sidebarOverlay').addEventListener('click', toggleMobileSidebar);
    $('sidebarToggle').addEventListener('click', () => sidebar.classList.toggle('collapsed'));
    ttsToggle.addEventListener('click', toggleTTS);
    $('modeCasual').addEventListener('click', () => setMode('casual'));
    $('modeInterview').addEventListener('click', () => setMode('interview'));

    messageInput.addEventListener('input', () => {
        sendBtn.disabled = !messageInput.value.trim() || state.streaming;
        autoResize();
    });
    messageInput.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (!sendBtn.disabled) send(); }
    });

    document.querySelectorAll('.prompt-card').forEach(c => {
        c.addEventListener('click', () => { messageInput.value = c.dataset.prompt; sendBtn.disabled = false; send(); });
    });
}

// ─── Health ────────────────────────────────
async function checkHealth() {
    try {
        const r = await fetch(`${API}/health`);
        const d = await r.json();
        if (d.status === 'ok') {
            statusDot.className = 'status-dot online';
            statusText.textContent = d.active_model;
        } else {
            statusDot.className = 'status-dot offline';
            statusText.textContent = 'api offline';
        }
    } catch {
        statusDot.className = 'status-dot offline';
        statusText.textContent = 'backend offline';
    }
}

// ─── Sessions ──────────────────────────────
async function loadSessions() {
    try { state.sessions = await (await fetch(`${API}/sessions`)).json(); renderSessions(); } catch {}
}

function renderSessions() {
    sessionsList.innerHTML = '';
    state.sessions.forEach(s => {
        const d = document.createElement('div');
        d.className = `session-item${s.id === state.sessionId ? ' active' : ''}`;
        d.innerHTML = `<span class="session-title">${esc(s.title || 'New chat')}</span>
            <button class="delete-btn" title="Delete"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg></button>`;
        d.querySelector('.session-title').onclick = () => switchSession(s.id);
        d.querySelector('.delete-btn').onclick = e => { e.stopPropagation(); deleteSession(s.id); };
        sessionsList.appendChild(d);
    });
}

async function switchSession(id) {
    state.sessionId = id;
    const s = state.sessions.find(x => x.id === id);
    if (s) setMode(s.mode, false);
    renderSessions();
    welcomeScreen.style.display = 'none';
    messagesArea.className = 'messages-area active';
    messagesArea.innerHTML = '';
    sidebar.classList.remove('mobile-open');
    $('sidebarOverlay').classList.add('hidden');
    try {
        const msgs = await (await fetch(`${API}/sessions/${id}/messages`)).json();
        msgs.forEach(m => renderMsg(m));
        scrollEnd();
    } catch {}
}

async function deleteSession(id) {
    try {
        await fetch(`${API}/sessions/${id}`, { method: 'DELETE' });
        if (state.sessionId === id) { state.sessionId = null; showWelcome(); }
        await loadSessions();
    } catch {}
}

function newChat() {
    state.sessionId = null;
    showWelcome();
    renderSessions();
    sidebar.classList.remove('mobile-open');
    $('sidebarOverlay').classList.add('hidden');
}

function showWelcome() {
    welcomeScreen.style.display = '';
    messagesArea.className = 'messages-area';
    messagesArea.innerHTML = '';
}

function setMode(m) {
    state.mode = m;
    $('modeCasual').classList.toggle('active', m === 'casual');
    $('modeInterview').classList.toggle('active', m === 'interview');
}

// ─── Send + Stream ─────────────────────────
async function send() {
    const text = messageInput.value.trim();
    if (!text || state.streaming) return;

    messageInput.value = '';
    sendBtn.disabled = true;
    autoResize();
    state.streaming = true;
    sendBtn.classList.add('hidden');
    stopBtn.classList.remove('hidden');

    welcomeScreen.style.display = 'none';
    messagesArea.className = 'messages-area active';

    renderMsg({ role: 'user', original_text: text });

    // Typing dots
    const dots = mkTyping();
    messagesArea.appendChild(dots);
    scrollEnd();

    // Prepare streaming bot row
    const botRow = document.createElement('div');
    botRow.className = 'message-row bot';
    botRow.innerHTML = `<div class="message-wrapper">
        <div class="message-avatar">C</div>
        <div class="message-body">
            <div class="message-sender">chummah</div>
            <div class="message-text"><span class="streaming-cursor"></span></div>
            <div class="corrections-container"></div>
            <div class="message-actions">
                <button class="action-btn speak-btn" title="Read aloud"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 010 7.07"/></svg></button>
            </div>
        </div>
    </div>`;

    state.abort = new AbortController();
    let rawStream = '';
    let parsed = null;

    try {
        const res = await fetch(`${API}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, mode: state.mode, session_id: state.sessionId }),
            signal: state.abort.signal,
        });

        dots.remove();
        messagesArea.appendChild(botRow);
        const textEl = botRow.querySelector('.message-text');
        const corrEl = botRow.querySelector('.corrections-container');

        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = '';
        let evtType = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += dec.decode(value, { stream: true });
            const lines = buf.split('\n');
            buf = lines.pop() || '';

            for (const ln of lines) {
                if (ln.startsWith('event: ')) {
                    evtType = ln.slice(7).trim();
                } else if (ln.startsWith('data: ') && evtType) {
                    try {
                        const d = JSON.parse(ln.slice(6));
                        if (evtType === 'meta' && d.session_id) state.sessionId = d.session_id;
                        if (evtType === 'token') {
                            rawStream += d.token || '';
                            // Live-extract reply from streaming JSON
                            const partial = extractReply(rawStream);
                            if (partial) {
                                textEl.innerHTML = fmt(partial) + '<span class="streaming-cursor"></span>';
                            }
                        }
                        if (evtType === 'corrections') {
                            parsed = d;
                            textEl.innerHTML = fmt(d.reply || rawStream);
                            renderCorrections(d, corrEl);
                        }
                        if (evtType === 'done') {
                            if (d.session_title) { await loadSessions(); renderSessions(); }
                        }
                        if (evtType === 'error') {
                            textEl.innerHTML = `<span style="color:var(--error)">${esc(d.error)}</span>`;
                        }
                    } catch {}
                    evtType = null;
                }
            }
            scrollEnd();
        }

        // If corrections event never came, try to parse raw stream
        if (!parsed) {
            textEl.innerHTML = fmt(extractReply(rawStream) || rawStream);
        }

        // TTS
        if (state.tts && parsed?.reply) speak(parsed.reply);

        const sb = botRow.querySelector('.speak-btn');
        if (sb && parsed?.reply) sb.onclick = () => speak(parsed.reply);

    } catch (e) {
        dots.remove();
        if (e.name !== 'AbortError') renderError('Connection failed. Is the backend running?');
    } finally {
        state.streaming = false;
        state.abort = null;
        stopBtn.classList.add('hidden');
        sendBtn.classList.remove('hidden');
        sendBtn.disabled = !messageInput.value.trim();
    }
}

/**
 * Extract the "reply" value from a partially-streamed JSON string.
 * The model outputs: {"reply": "some text...", "grammar_fixes": [...] ...}
 * We grab everything inside the "reply" value as it streams.
 */
function extractReply(raw) {
    // Find "reply" key and extract its string value (potentially incomplete)
    const m = raw.match(/"reply"\s*:\s*"((?:[^"\\]|\\.)*)(?:"|$)/s);
    if (!m) return null;
    // Unescape JSON string escapes
    return m[1].replace(/\\n/g, '\n').replace(/\\"/g, '"').replace(/\\\\/g, '\\').replace(/\\t/g, '\t');
}

// ─── Render ────────────────────────────────
function renderMsg(msg) {
    const row = document.createElement('div');
    row.className = `message-row ${msg.role === 'user' ? 'user' : 'bot'}`;

    if (msg.role === 'user') {
        row.innerHTML = `<div class="message-wrapper">
            <div class="message-avatar">U</div>
            <div class="message-body">
                <div class="message-sender">you</div>
                <div class="message-text">${fmt(msg.original_text || '')}</div>
            </div></div>`;
    } else {
        row.innerHTML = `<div class="message-wrapper">
            <div class="message-avatar">C</div>
            <div class="message-body">
                <div class="message-sender">chummah</div>
                <div class="message-text">${fmt(msg.display_text || '')}</div>
                <div class="corrections-container"></div>
                <div class="message-actions">
                    <button class="action-btn speak-btn" title="Read aloud"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 010 7.07"/></svg></button>
                </div>
            </div></div>`;
        if (msg.corrections) renderCorrections(msg.corrections, row.querySelector('.corrections-container'));
        const sb = row.querySelector('.speak-btn');
        if (sb) sb.onclick = () => speak(msg.display_text || '');
    }
    messagesArea.appendChild(row);
}

function renderCorrections(data, el) {
    if (!el) return;
    const ng = data.grammar_fixes?.length || 0;
    const nv = data.vocab_tips?.length || 0;
    const na = data.alt_phrasings?.length || 0;
    if (!ng && !nv && !na) return;

    const toggle = document.createElement('button');
    toggle.className = 'correction-toggle';
    toggle.innerHTML = `<span class="chevron">&#9654;</span> ${ng + nv} corrections, ${na} alternatives`;

    const body = document.createElement('div');
    body.className = 'corrections-body';

    if (ng) {
        const s = document.createElement('div');
        s.className = 'correction-section grammar';
        s.innerHTML = `<div class="correction-label">grammar</div>`;
        data.grammar_fixes.forEach(f => {
            const d = document.createElement('div'); d.className = 'fix-item';
            d.innerHTML = `<span class="original">${esc(f.original||'')}</span><span class="arrow"> → </span><span class="corrected">${esc(f.corrected||'')}</span>${f.error ? `<span class="error-note">${esc(f.error)}</span>` : ''}`;
            s.appendChild(d);
        });
        body.appendChild(s);
    }
    if (nv) {
        const s = document.createElement('div');
        s.className = 'correction-section vocab';
        s.innerHTML = `<div class="correction-label">vocabulary</div>`;
        data.vocab_tips.forEach(t => {
            const d = document.createElement('div'); d.className = 'fix-item';
            d.innerHTML = `<span class="original">${esc(t.original||'')}</span><span class="arrow"> → </span><span class="corrected">${esc(t.suggestion||'')}</span>${t.reason ? `<span class="reason">${esc(t.reason)}</span>` : ''}`;
            s.appendChild(d);
        });
        body.appendChild(s);
    }
    if (na) {
        const s = document.createElement('div');
        s.className = 'correction-section alt';
        s.innerHTML = `<div class="correction-label">alternatives</div>`;
        data.alt_phrasings.forEach(a => {
            const d = document.createElement('div'); d.className = 'alt-item'; d.textContent = a;
            s.appendChild(d);
        });
        body.appendChild(s);
    }

    toggle.onclick = () => { toggle.classList.toggle('expanded'); body.classList.toggle('visible'); };
    el.appendChild(toggle);
    el.appendChild(body);
}

function renderError(t) {
    const r = document.createElement('div');
    r.className = 'message-row bot';
    r.innerHTML = `<div class="message-wrapper"><div class="message-avatar" style="background:var(--error)">!</div>
        <div class="message-body"><div class="message-text" style="color:var(--error)">${esc(t)}</div></div></div>`;
    messagesArea.appendChild(r);
    scrollEnd();
}

function mkTyping() {
    const r = document.createElement('div');
    r.className = 'message-row bot';
    r.innerHTML = `<div class="message-wrapper"><div class="message-avatar">C</div>
        <div class="message-body"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div></div></div>`;
    return r;
}

// ─── Voice ─────────────────────────────────

/**
 * Check if the Web Speech API is available in this browser.
 * Returns the constructor or null.
 */
function getSpeechRecognitionClass() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function initVoice() {
    if (!getSpeechRecognitionClass()) {
        micBtn.title = 'Voice not supported in this browser';
        micBtn.style.opacity = '0.3';
    }
    // Nothing else to do — we create a fresh instance on every mic press.
}

/**
 * Build a fresh SpeechRecognition instance each time the user taps the mic.
 * Re-creating avoids stale internal state in the browser's STT engine that
 * degrades accuracy over successive recordings.
 */
function buildRecognition(onFinalTranscript) {
    const SR = getSpeechRecognitionClass();
    if (!SR) return null;

    const rec = new SR();

    // ── Accuracy settings ──────────────────────────────────────────────────
    // en-US gives the best model quality. If users speak Indian English,
    // 'en-IN' can help — toggling is also an option but en-US tends to be
    // more accurate overall for non-native speakers as well.
    rec.lang = 'en-US';

    // Continuous mode: keeps the session open across brief pauses so users
    // can speak full sentences without the mic cutting out mid-utterance.
    rec.continuous = true;

    // Show live interim words while the user is still speaking.
    rec.interimResults = true;

    // Ask the engine for its top 3 guesses; we always pick the one with the
    // highest confidence score rather than blindly taking index 0.
    rec.maxAlternatives = 3;

    let finalTranscript = '';
    let silenceTimer = null;

    const resetSilenceTimer = () => {
        clearTimeout(silenceTimer);
        // Auto-stop after 3 s of silence so the session doesn't hang open.
        silenceTimer = setTimeout(() => {
            try { rec.stop(); } catch {}
        }, 3000);
    };

    rec.onstart = () => {
        state.recording = true;
        finalTranscript = '';
        micBtn.classList.add('recording');
        recordingIndicator.classList.remove('hidden');
        messageInput.placeholder = 'listening...';
        messageInput.value = '';
        sendBtn.disabled = true;
        resetSilenceTimer();
    };

    rec.onresult = (e) => {
        resetSilenceTimer(); // user is still speaking — push the silence timer

        let interim = '';
        for (let i = e.resultIndex; i < e.results.length; i++) {
            const result = e.results[i];

            if (result.isFinal) {
                // Pick the alternative with the highest confidence for accuracy.
                let best = result[0];
                for (let a = 1; a < result.length; a++) {
                    if (result[a].confidence > best.confidence) best = result[a];
                }
                finalTranscript += best.transcript;
            } else {
                // For interim, also use the highest-confidence alternative.
                let best = result[0];
                for (let a = 1; a < result.length; a++) {
                    if (result[a].confidence > best.confidence) best = result[a];
                }
                interim = best.transcript;
            }
        }

        // Show the running transcript in the input so users can see it live.
        messageInput.value = finalTranscript + interim;
        sendBtn.disabled = !(finalTranscript + interim).trim();
        autoResize();
    };

    rec.onend = () => {
        clearTimeout(silenceTimer);
        state.recording = false;
        micBtn.classList.remove('recording');
        recordingIndicator.classList.add('hidden');
        messageInput.placeholder = 'say something...';

        const text = messageInput.value.trim();
        sendBtn.disabled = !text;
        if (text) onFinalTranscript(text);
    };

    rec.onerror = (e) => {
        clearTimeout(silenceTimer);
        console.warn('Speech error:', e.error);

        if (e.error === 'no-speech') {
            // Silently ignore — onend will fire and clean up.
            return;
        }

        state.recording = false;
        micBtn.classList.remove('recording');
        recordingIndicator.classList.add('hidden');

        if (e.error === 'not-allowed') {
            messageInput.placeholder = 'microphone blocked — check browser permissions';
        } else {
            messageInput.placeholder = 'say something...';
        }
    };

    return rec;
}

function toggleMic() {
    if (!getSpeechRecognitionClass()) return;
    if (state.streaming) return; // Don't record while streaming

    if (state.recording) {
        // User tapped mic again to stop manually.
        try { state.recognition?.stop(); } catch {}
        return;
    }

    // Build a fresh recognition session for best accuracy.
    state.recognition = buildRecognition((text) => {
        // Called when the session ends with a non-empty transcript.
        // Just enable send — user can review before sending.
        sendBtn.disabled = !text;
    });

    if (!state.recognition) return;

    try {
        state.recognition.start();
    } catch (e) {
        console.warn('Could not start recognition:', e);
    }
}

// ─── TTS ───────────────────────────────────
function speak(text) {
    if (!text || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 0.9;
    u.pitch = 1.0;
    u.lang = 'en-US';
    const voices = window.speechSynthesis.getVoices();
    const v = voices.find(v => v.name.includes('Google') && v.lang.startsWith('en'))
        || voices.find(v => v.lang.startsWith('en-US'))
        || voices.find(v => v.lang.startsWith('en'));
    if (v) u.voice = v;
    window.speechSynthesis.speak(u);
}

function toggleTTS() {
    state.tts = !state.tts;
    ttsToggle.classList.toggle('active', state.tts);
    ttsLabel.textContent = state.tts ? 'voice on' : 'voice off';
    if (!state.tts) window.speechSynthesis?.cancel();
}

if (window.speechSynthesis) window.speechSynthesis.onvoiceschanged = () => {};

// ─── Utils ─────────────────────────────────
function scrollEnd() { requestAnimationFrame(() => { chatContainer.scrollTop = chatContainer.scrollHeight; }); }
function autoResize() { messageInput.style.height = 'auto'; messageInput.style.height = Math.min(messageInput.scrollHeight, 160) + 'px'; }
function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function fmt(t) { return esc(t).replace(/\n/g, '<br>'); }
function toggleMobileSidebar() { sidebar.classList.toggle('mobile-open'); $('sidebarOverlay').classList.toggle('hidden'); }
