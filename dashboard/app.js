// ═══════════════════════════════════════════════════════════════
// Dobot Sort Master — Dashboard Client Logic
// Simulation engine + WebSocket live telemetry hookup
// ═══════════════════════════════════════════════════════════════

// ── Timing config (matches config.py) ──────────────────────────
const TIMING = {
    CAPTURE_DELAY:   150,   // ms after IR1 before camera snaps
    SERVO_MOVE:     1200,   // ms — servo travel to push angle
    SERVO_HOLD:     4000,   // ms — hold at push position
    SERVO_RETURN:   1200,   // ms — return to neutral
};

// ── Application state ──────────────────────────────────────────
const S = {
    simRunning: true,
    simTimer:   null,
    wsConn:     null,
    wsOk:       false,
    counts:     { green:0, blue:0, yellow:0, red:0, unknown:0 },
    total:      0,
    queue:      [],          // string labels
    cubes:      [],          // visual cube objects on belt
    nextId:     0,
    beltPaused: false,
};

// ── DOM refs ───────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const DOM = {
    clock:     $('clock'),
    statusDot: $('statusDot'),
    statusText:$('statusText'),
    modePill:  $('modePill'),
    // Scanner
    scannerFrame: $('scannerFrame'),
    roi:       $('roi'),
    roiTag:    $('roiTag'),
    flash:     $('flash'),
    clsColor:  $('clsColor'),
    clsBar:    $('clsBar'),
    clsConf:   $('clsConf'),
    clsModel:  $('clsModel'),
    // Controls
    btnInject: $('btnInject'),
    btnToggle: $('btnToggle'),
    btnReset:  $('btnReset'),
    // Queue
    trackItems:$('trackItems'),
    queueCount:$('queueCount'),
    // Stats
    totalCount:$('totalCount'),
    cntGreen:  $('cntGreen'),  barGreen:  $('barGreen'),
    cntBlue:   $('cntBlue'),   barBlue:   $('barBlue'),
    cntYellow: $('cntYellow'), barYellow: $('barYellow'),
    cntRed:    $('cntRed'),    barRed:    $('barRed'),
    cntUnknown:$('cntUnknown'),barUnknown:$('barUnknown'),
    // Log
    logScroll: $('logScroll'),
};

// ═══════════════════════════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════════════════════════

function pad(n) { return String(n).padStart(2, '0'); }

function timestamp() {
    const d = new Date();
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

// Clock tick
function tickClock() { DOM.clock.textContent = timestamp(); }
setInterval(tickClock, 1000);
tickClock();

// Logger
function log(msg, type = '') {
    const div = document.createElement('div');
    div.className = 'log-line' + (type ? ' ' + type : '');
    div.textContent = `[${timestamp()}] ${msg}`;
    DOM.logScroll.appendChild(div);
    DOM.logScroll.scrollTop = DOM.logScroll.scrollHeight;
    // Cap at 80 lines
    while (DOM.logScroll.children.length > 80) DOM.logScroll.removeChild(DOM.logScroll.firstChild);
}

// ═══════════════════════════════════════════════════════════════
// UI UPDATE HELPERS
// ═══════════════════════════════════════════════════════════════

function refreshStats() {
    DOM.totalCount.textContent = S.total;
    const mx = Math.max(1, S.total);
    const up = (key, cnt, bar) => {
        cnt.textContent = S.counts[key];
        bar.style.width = `${(S.counts[key] / mx) * 100}%`;
    };
    up('green',  DOM.cntGreen,  DOM.barGreen);
    up('blue',   DOM.cntBlue,   DOM.barBlue);
    up('yellow', DOM.cntYellow, DOM.barYellow);
    up('red',    DOM.cntRed,    DOM.barRed);
    up('unknown',DOM.cntUnknown,DOM.barUnknown);
}

function refreshQueueBadge() {
    DOM.queueCount.textContent = `${S.queue.length} queued`;
}

function setBelt(running) {
    S.beltPaused = !running;
    document.querySelector('.track-stripe').style.animationPlayState = running ? 'running' : 'paused';
}

// ── Scanner ROI ────────────────────────────────────────────────
function showROI(color, conf, model) {
    const roi = DOM.roi;
    // Random bbox within scanner frame
    const fw = DOM.scannerFrame.clientWidth;
    const fh = DOM.scannerFrame.clientHeight;
    const bw = 100 + Math.random() * 50;
    const bh = 100 + Math.random() * 50;
    const bx = (fw - bw) * (.3 + Math.random() * .4);
    const by = (fh - bh) * (.2 + Math.random() * .5);

    roi.style.left   = bx + 'px';
    roi.style.top    = by + 'px';
    roi.style.width  = bw + 'px';
    roi.style.height = bh + 'px';
    roi.className = 'roi visible c-' + color;
    DOM.roiTag.textContent = `${color.toUpperCase()} ${(conf * 100).toFixed(0)}%`;

    // Update details strip
    DOM.clsColor.textContent = color.toUpperCase();
    DOM.clsColor.style.color = `var(--${color === 'unknown' ? 'unknown' : color})`;
    DOM.clsBar.style.width = `${conf * 100}%`;
    DOM.clsBar.style.background = `var(--${color === 'unknown' ? 'unknown' : color})`;
    DOM.clsConf.textContent = `${(conf * 100).toFixed(1)}%`;
    DOM.clsModel.textContent = model;

    // Flash
    DOM.flash.classList.add('fire');
    setTimeout(() => DOM.flash.classList.remove('fire'), 250);
}

function hideROI() {
    DOM.roi.classList.remove('visible');
}

// ═══════════════════════════════════════════════════════════════
// CONVEYOR CUBE ENGINE
// ═══════════════════════════════════════════════════════════════

function spawnCube(color) {
    const id = S.nextId++;
    const el = document.createElement('div');
    el.className = `cube c-${color}`;
    el.textContent = color.substring(0, 2).toUpperCase();
    el.style.left = '0%';
    DOM.trackItems.appendChild(el);

    const cube = { id, el, color, pct: 0, phase: 'to_ir1' };
    S.cubes.push(cube);
    return cube;
}

function removeCube(id) {
    const i = S.cubes.findIndex(c => c.id === id);
    if (i === -1) return;
    const c = S.cubes[i];
    if (c.el.parentNode) c.el.parentNode.removeChild(c.el);
    S.cubes.splice(i, 1);
}

// Percentages:  IR1 = 18%,  IR2 = 52%,  IR3 = 84%
const ZONE = { ir1: 18, ir2: 52, ir3: 84 };
const STEP = 0.45; // pct per tick

function tick() {
    S.cubes.forEach(c => {
        switch (c.phase) {

        // ── Moving to camera zone ───────────────────────
        case 'to_ir1':
            if (S.beltPaused) return;
            c.pct += STEP;
            c.el.style.left = c.pct + '%';
            if (c.pct >= ZONE.ir1) {
                c.pct = ZONE.ir1;
                c.el.style.left = c.pct + '%';
                c.phase = 'scanning';
                setBelt(false);
                log(`[IR1] Cube detected — pausing belt, capturing frame.`, 'sys');

                // Simulate classification after short delay
                setTimeout(() => {
                    const conf = 0.85 + Math.random() * 0.15;
                    const model = Math.random() > 0.4 ? 'KNN' : 'SVM';
                    showROI(c.color, conf, model);
                    S.queue.push(c.color);
                    refreshQueueBadge();
                    log(`[ML] Classified ${c.color.toUpperCase()} (${(conf*100).toFixed(1)}%) via ${model}`);
                    setBelt(true);
                    c.phase = 'to_ir2';
                }, TIMING.CAPTURE_DELAY + 350);
            }
            break;

        // ── Moving to Servo 1 zone ──────────────────────
        case 'to_ir2':
            if (S.beltPaused) return;
            c.pct += STEP;
            c.el.style.left = c.pct + '%';
            if (c.pct >= ZONE.ir2) {
                c.pct = ZONE.ir2;
                c.el.style.left = c.pct + '%';
                if (c.color === 'green' || c.color === 'blue') {
                    c.phase = 'sorting_ir2';
                    setBelt(false);
                    hideROI();
                    log(`[IR2] Stopping belt — Servo 1 pushing ${c.color.toUpperCase()}`, 'warn');

                    const holdTime = TIMING.SERVO_MOVE + TIMING.SERVO_HOLD;
                    setTimeout(() => {
                        c.el.style.transform = 'translateY(35px)';
                        c.el.style.opacity = '0';
                        log(`[ESP32] Servo 1 push done, returning to neutral.`);

                        setTimeout(() => {
                            S.queue.shift();
                            refreshQueueBadge();
                            S.counts[c.color]++;
                            S.total++;
                            refreshStats();
                            log(`[SORTED] ${c.color.toUpperCase()} → bin. Belt resumed.`, 'sys');
                            removeCube(c.id);
                            setBelt(true);
                        }, TIMING.SERVO_RETURN);
                    }, holdTime);
                } else {
                    log(`[IR2] ${c.color.toUpperCase()} passes through to Servo 2.`);
                    c.phase = 'to_ir3';
                }
            }
            break;

        // ── Moving to Servo 2 zone ──────────────────────
        case 'to_ir3':
            if (S.beltPaused) return;
            c.pct += STEP;
            c.el.style.left = c.pct + '%';
            if (c.pct >= ZONE.ir3) {
                c.pct = ZONE.ir3;
                c.el.style.left = c.pct + '%';
                if (c.color === 'yellow' || c.color === 'red') {
                    c.phase = 'sorting_ir3';
                    setBelt(false);
                    hideROI();
                    log(`[IR3] Stopping belt — Servo 2 pushing ${c.color.toUpperCase()}`, 'warn');

                    const holdTime = TIMING.SERVO_MOVE + TIMING.SERVO_HOLD;
                    setTimeout(() => {
                        c.el.style.transform = 'translateY(35px)';
                        c.el.style.opacity = '0';
                        log(`[ESP32] Servo 2 push done, returning to neutral.`);

                        setTimeout(() => {
                            S.queue.shift();
                            refreshQueueBadge();
                            S.counts[c.color]++;
                            S.total++;
                            refreshStats();
                            log(`[SORTED] ${c.color.toUpperCase()} → bin. Belt resumed.`, 'sys');
                            removeCube(c.id);
                            setBelt(true);
                        }, TIMING.SERVO_RETURN);
                    }, holdTime);
                } else {
                    // unknown — pass through
                    S.queue.shift();
                    refreshQueueBadge();
                    S.counts.unknown++;
                    S.total++;
                    refreshStats();
                    log(`[IR3] UNKNOWN cube passed through unsorted.`, 'warn');
                    c.phase = 'exit';
                }
            }
            break;

        // ── Exiting belt ────────────────────────────────
        case 'exit':
            if (S.beltPaused) return;
            c.pct += STEP;
            c.el.style.left = c.pct + '%';
            if (c.pct >= 100) {
                c.el.style.opacity = '0';
                c.phase = 'gone';
                setTimeout(() => removeCube(c.id), 400);
            }
            break;
        }
    });
}
setInterval(tick, 50);

// ═══════════════════════════════════════════════════════════════
// SIMULATION AUTO-FEED
// ═══════════════════════════════════════════════════════════════

const COLORS = ['green','blue','yellow','red','unknown'];
const WEIGHTS = [0.25, 0.25, 0.22, 0.22, 0.06];

function randomColor() {
    let r = Math.random(), s = 0;
    for (let i = 0; i < COLORS.length; i++) {
        s += WEIGHTS[i];
        if (r <= s) return COLORS[i];
    }
    return COLORS[0];
}

function injectCube() {
    // Don't inject if a cube is currently in the first 15% of the belt
    if (S.cubes.some(c => c.pct < 15)) return;
    const color = randomColor();
    spawnCube(color);
}

function startSim() {
    if (S.simTimer) return;
    S.simRunning = true;
    DOM.modePill.textContent = 'SIMULATION';
    S.simTimer = setInterval(injectCube, 8500);
    injectCube();
    log('[SYSTEM] Auto-simulation started.');
}

function stopSim() {
    S.simRunning = false;
    DOM.modePill.textContent = 'PAUSED';
    if (S.simTimer) { clearInterval(S.simTimer); S.simTimer = null; }
    log('[SYSTEM] Auto-simulation paused.');
}

// ═══════════════════════════════════════════════════════════════
// WEBSOCKET CLIENT (Production hookup)
// ═══════════════════════════════════════════════════════════════

function connectWS() {
    try { S.wsConn = new WebSocket('ws://localhost:8765'); } catch(e) { return; }

    S.wsConn.onopen = () => {
        S.wsOk = true;
        stopSim();
        DOM.modePill.textContent = 'LIVE';
        log('[WS] Connected to Python backend.', 'sys');
    };
    S.wsConn.onmessage = (evt) => {
        try { handleWS(JSON.parse(evt.data)); } catch(e) {}
    };
    S.wsConn.onclose = () => {
        if (S.wsOk) {
            S.wsOk = false;
            log('[WS] Disconnected. Returning to simulation.', 'err');
            startSim();
        }
        setTimeout(connectWS, 5000);
    };
    S.wsConn.onerror = () => {};
}

function handleWS(d) {
    switch (d.event) {
    case 'init':
        if (d.counts) { S.counts = { ...d.counts }; S.total = Object.values(S.counts).reduce((a,b)=>a+b,0); refreshStats(); }
        if (d.queue)  { S.queue = [...d.queue]; refreshQueueBadge(); }
        log(`[WS] Handshake received. Status: ${d.status}`);
        break;
    case 'classified':
        showROI(d.color, d.confidence || 1, d.model || 'KNN');
        if (d.queue) { S.queue = [...d.queue]; refreshQueueBadge(); }
        log(`[WS] Classified: ${d.color.toUpperCase()}`, 'sys');
        break;
    case 'sorted':
        hideROI();
        if (d.counts) { S.counts = { ...d.counts }; S.total = Object.values(S.counts).reduce((a,b)=>a+b,0); refreshStats(); }
        if (d.queue)  { S.queue = [...d.queue]; refreshQueueBadge(); }
        log(`[WS] Sorted: ${d.color.toUpperCase()}`, 'sys');
        break;
    case 'halt':
        log(`[WS] SYSTEM HALTED — ${d.reason}`, 'err');
        break;
    }
}

// ═══════════════════════════════════════════════════════════════
// BUTTON HANDLERS
// ═══════════════════════════════════════════════════════════════

DOM.btnInject.addEventListener('click', () => {
    const color = randomColor();
    spawnCube(color);
    log(`[USER] Placed mock ${color.toUpperCase()} cube on belt.`);
});

DOM.btnToggle.addEventListener('click', () => {
    S.simRunning ? stopSim() : startSim();
});

DOM.btnReset.addEventListener('click', () => {
    S.counts = { green:0, blue:0, yellow:0, red:0, unknown:0 };
    S.total = 0;
    refreshStats();
    log('[SYSTEM] Counters reset.');
});

// ═══════════════════════════════════════════════════════════════
// BOOT
// ═══════════════════════════════════════════════════════════════

startSim();
connectWS();
log('[SYSTEM] Dashboard ready. Auto-simulation active.', 'sys');
