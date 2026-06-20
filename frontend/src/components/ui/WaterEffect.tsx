import { useEffect, useRef } from 'react';

/* ═══════════════════════════════════════════════════════════════════════════
   WABAG WATER EFFECT  —  Designed around VA Tech WABAG's core identity:
   Water treatment · Aeration · Purification · Clean water flow

   Visual metaphor: looking through the glass wall of a water treatment tank —
   bubbles rising from aerators below, water surface rippling above,
   occasional droplets disturbing the calm surface.

   Palette: WABAG ocean blues  →  #0077b6 · #0096c7 · #00b4d8 · #48cae4 · #90e0ef
═══════════════════════════════════════════════════════════════════════════ */

// ─── Types ────────────────────────────────────────────────────────────────────

type Bubble = {
  x: number; y: number;
  r: number;
  vy: number;           // rise speed
  wobble: number;       // horizontal oscillation amplitude
  wobbleSpeed: number;
  phase: number;
  opacity: number;
  popping: boolean;
  popR: number;
};

type Drop = {
  x: number; y: number;
  vy: number;
  r: number;
  opacity: number;
  active: boolean;
  impactY: number;      // y where it hits the "surface"
};

type Ring = {
  x: number; y: number;
  r: number;
  maxR: number;
  speed: number;        // starts fast, decelerates
  opacity: number;
  lineW: number;
};

// ─── Config ───────────────────────────────────────────────────────────────────

const WABAG = {
  deep:   { r: 0,   g: 119, b: 182 },  // #0077b6
  mid:    { r: 0,   g: 150, b: 199 },  // #0096c7
  light:  { r: 0,   g: 180, b: 216 },  // #00b4d8
  bright: { r: 72,  g: 202, b: 228 },  // #48cae4
  pale:   { r: 144, g: 224, b: 239 },  // #90e0ef
};
function wc(c: typeof WABAG[keyof typeof WABAG], a: number) {
  return `rgba(${c.r},${c.g},${c.b},${a})`;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function randBetween(a: number, b: number) { return a + Math.random() * (b - a); }

function makeBubble(w: number, h: number, startAtBottom = false): Bubble {
  const r = randBetween(1.2, 5.5);
  return {
    x:          randBetween(0, w),
    y:          startAtBottom ? h + r + randBetween(0, h * 0.4) : randBetween(h * 0.2, h + r),
    r,
    vy:         randBetween(0.28, 0.85),
    wobble:     randBetween(0.4, 1.4),
    wobbleSpeed:randBetween(0.012, 0.028),
    phase:      randBetween(0, Math.PI * 2),
    opacity:    randBetween(0.06, 0.22),
    popping:    false,
    popR:       0,
  };
}

function makeDrop(w: number): Drop {
  return {
    x:       randBetween(w * 0.05, w * 0.95),
    y:       -20,
    vy:      randBetween(1.8, 3.2),
    r:       randBetween(2.2, 3.8),
    opacity: randBetween(0.25, 0.55),
    active:  true,
    impactY: randBetween(window.innerHeight * 0.55, window.innerHeight * 0.85),
  };
}

// ─── Draw Bubble ──────────────────────────────────────────────────────────────

function drawBubble(ctx: CanvasRenderingContext2D, b: Bubble) {
  if (b.popping) {
    // Pop ring expands and fades
    ctx.save();
    ctx.strokeStyle = wc(WABAG.bright, Math.max(0, 0.5 - b.popR / (b.r * 6)));
    ctx.lineWidth   = 0.8;
    ctx.beginPath();
    ctx.arc(b.x, b.y, b.r + b.popR, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
    return;
  }

  ctx.save();
  ctx.translate(b.x, b.y);

  // Ambient glow (faint halo)
  const glow = ctx.createRadialGradient(0, 0, b.r * 0.5, 0, 0, b.r * 2.8);
  glow.addColorStop(0,   wc(WABAG.bright, b.opacity * 0.2));
  glow.addColorStop(1,   'rgba(0,0,0,0)');
  ctx.beginPath();
  ctx.arc(0, 0, b.r * 2.8, 0, Math.PI * 2);
  ctx.fillStyle = glow;
  ctx.fill();

  // Bubble body — transparent, edge-lit
  const body = ctx.createRadialGradient(-b.r * 0.3, -b.r * 0.3, 0, 0, 0, b.r);
  body.addColorStop(0,   wc(WABAG.pale,   b.opacity * 0.12));
  body.addColorStop(0.6, wc(WABAG.light,  b.opacity * 0.07));
  body.addColorStop(1,   wc(WABAG.deep,   b.opacity * 0.04));
  ctx.beginPath();
  ctx.arc(0, 0, b.r, 0, Math.PI * 2);
  ctx.fillStyle = body;
  ctx.fill();

  // Rim — bright edge
  ctx.beginPath();
  ctx.arc(0, 0, b.r, 0, Math.PI * 2);
  ctx.strokeStyle = wc(WABAG.bright, b.opacity * 0.7);
  ctx.lineWidth   = 0.6;
  ctx.stroke();

  // Main highlight — top-left crescent (real bubble physics)
  const hl1 = ctx.createRadialGradient(-b.r * 0.38, -b.r * 0.42, 0, -b.r * 0.3, -b.r * 0.35, b.r * 0.52);
  hl1.addColorStop(0,   `rgba(255,255,255,${b.opacity * 0.95})`);
  hl1.addColorStop(0.5, `rgba(202,240,248,${b.opacity * 0.35})`);
  hl1.addColorStop(1,   'rgba(202,240,248,0)');
  ctx.beginPath();
  ctx.arc(0, 0, b.r, 0, Math.PI * 2);
  ctx.fillStyle = hl1;
  ctx.fill();

  // Micro spark — tiny bright dot
  ctx.beginPath();
  ctx.arc(-b.r * 0.42, -b.r * 0.46, b.r * 0.14, 0, Math.PI * 2);
  ctx.fillStyle = `rgba(255,255,255,${b.opacity * 0.9})`;
  ctx.fill();

  ctx.restore();
}

// ─── Draw Drop ────────────────────────────────────────────────────────────────

function drawDrop(ctx: CanvasRenderingContext2D, d: Drop) {
  const stretch = 1 + d.vy * 0.28;
  const rw = d.r, rh = d.r * stretch;

  ctx.save();
  ctx.translate(d.x, d.y);

  // Outer glow
  const og = ctx.createRadialGradient(0, 0, 0, 0, 0, rh * 2.5);
  og.addColorStop(0,   wc(WABAG.bright, d.opacity * 0.15));
  og.addColorStop(1,   'rgba(0,0,0,0)');
  ctx.beginPath();
  ctx.ellipse(0, 0, rh * 2.5, rh * 2.5, 0, 0, Math.PI * 2);
  ctx.fillStyle = og;
  ctx.fill();

  // Body — teardrop
  ctx.beginPath();
  ctx.moveTo(0, -rh * 2.2);
  ctx.bezierCurveTo( rw * 1.05, -rh * 0.75,  rw * 1.05,  rh * 0.65,  0,  rh * 1.1);
  ctx.bezierCurveTo(-rw * 1.05,  rh * 0.65, -rw * 1.05, -rh * 0.75,  0, -rh * 2.2);

  const body = ctx.createLinearGradient(-rw, -rh * 2.2, rw, rh * 1.1);
  body.addColorStop(0,    wc(WABAG.pale,   d.opacity * 0.9));
  body.addColorStop(0.35, wc(WABAG.bright, d.opacity));
  body.addColorStop(0.7,  wc(WABAG.mid,    d.opacity));
  body.addColorStop(1,    wc(WABAG.deep,   d.opacity * 0.8));
  ctx.fillStyle = body;
  ctx.fill();

  // Edge refraction
  ctx.strokeStyle = wc(WABAG.pale, d.opacity * 0.5);
  ctx.lineWidth   = 0.4;
  ctx.stroke();

  // Highlight
  ctx.beginPath();
  ctx.ellipse(-rw * 0.28, -rh * 1.4, rw * 0.22, rh * 0.48, -0.35, 0, Math.PI * 2);
  ctx.fillStyle = `rgba(255,255,255,${d.opacity * 0.8})`;
  ctx.fill();

  ctx.restore();
}

// ─── Draw Wave Lines ──────────────────────────────────────────────────────────

function drawWaves(ctx: CanvasRenderingContext2D, t: number, w: number, h: number) {
  const waveParams = [
    { freq: 0.008, amp: 22, speed: 0.3,  yBase: 0.30, op: 0.022 },
    { freq: 0.012, amp: 16, speed: 0.45, yBase: 0.45, op: 0.018 },
    { freq: 0.006, amp: 28, speed: 0.22, yBase: 0.60, op: 0.015 },
    { freq: 0.015, amp: 12, speed: 0.55, yBase: 0.72, op: 0.020 },
    { freq: 0.009, amp: 19, speed: 0.35, yBase: 0.82, op: 0.016 },
  ];

  waveParams.forEach(wp => {
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(0, h * wp.yBase);
    for (let x = 0; x <= w; x += 3) {
      const y = h * wp.yBase
        + Math.sin(x * wp.freq + t * wp.speed) * wp.amp
        + Math.sin(x * wp.freq * 1.6 + t * wp.speed * 0.7 + 1.2) * wp.amp * 0.4;
      ctx.lineTo(x, y);
    }
    ctx.strokeStyle = wc(WABAG.light, wp.op);
    ctx.lineWidth   = 1;
    ctx.stroke();
    ctx.restore();
  });
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function WaterEffect() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctxRaw = canvas.getContext('2d');
    if (!ctxRaw) return;
    const ctx: CanvasRenderingContext2D = ctxRaw;

    let w = window.innerWidth, h = window.innerHeight;
    const resize = () => {
      w = window.innerWidth; h = window.innerHeight;
      canvas.width  = w;
      canvas.height = h;
    };
    resize();
    window.addEventListener('resize', resize);

    // ── Init bubbles ──
    const BUBBLE_COUNT = 42;
    const bubbles: Bubble[] = Array.from({ length: BUBBLE_COUNT }, () =>
      makeBubble(w, h, false)
    );

    // ── Drops (max 3 active at a time, spawn slowly) ──
    const drops: Drop[] = [];
    let lastDropTime = 0;
    const DROP_INTERVAL_MS = 2200;

    // ── Ripple pool (auto + click) ──
    const rings: Ring[] = [];

    function spawnRipples(x: number, y: number, scale = 1.0) {
      [
        { maxR: 38  * scale, speed: 4.2, op: 0.75, lw: 1.8 },
        { maxR: 70  * scale, speed: 3.5, op: 0.55, lw: 1.3 },
        { maxR: 108 * scale, speed: 2.9, op: 0.38, lw: 1.0 },
        { maxR: 148 * scale, speed: 2.4, op: 0.24, lw: 0.7 },
        { maxR: 190 * scale, speed: 1.9, op: 0.14, lw: 0.5 },
        { maxR: 235 * scale, speed: 1.5, op: 0.07, lw: 0.4 },
      ].forEach(cfg => {
        rings.push({ x, y, r: 0, maxR: cfg.maxR, speed: cfg.speed, opacity: cfg.op, lineW: cfg.lw });
      });
    }

    const onClick = (e: MouseEvent) => spawnRipples(e.clientX, e.clientY, 1.3);
    window.addEventListener('click', onClick);

    // ── Tick ──
    let t      = 0;
    let raf: number;
    let lastTs = 0;

    function tick(ts: number) {
      const dt = Math.min(ts - lastTs, 32);
      lastTs   = ts;
      t        += dt * 0.001;

      ctx.clearRect(0, 0, w, h);

      // 1. Subtle animated wave lines (water surface texture)
      drawWaves(ctx, t, w, h);

      // 2. Bubbles rising
      bubbles.forEach(b => {
        if (b.popping) {
          b.popR += 0.9;
          if (b.popR > b.r * 5) {
            Object.assign(b, makeBubble(w, h, true));
            b.popping = false; b.popR = 0;
          }
        } else {
          b.y -= b.vy;
          b.x += Math.sin(t * b.wobbleSpeed * 60 + b.phase) * b.wobble * 0.06;

          if (b.y < -b.r * 3) {
            // bubble reaches surface — pop
            b.popping = true;
            b.popR    = 0;
          }
        }
        drawBubble(ctx, b);
      });

      // 3. Spawn drops
      if (ts - lastDropTime > DROP_INTERVAL_MS && drops.filter(d => d.active).length < 3) {
        drops.push(makeDrop(w));
        lastDropTime = ts;
        // Remove old completed drops
        while (drops.length > 12) drops.shift();
      }

      // 4. Update + draw drops
      drops.forEach(d => {
        if (!d.active) return;
        d.vy += 0.06;   // gravity
        d.y  += d.vy;

        if (d.y >= d.impactY) {
          // Impact — spawn ripples + mark done
          spawnRipples(d.x, d.impactY, 0.85);
          d.active = false;
        } else {
          drawDrop(ctx, d);
        }
      });

      // 5. Ripple rings (decelerate with easing)
      for (let ri = rings.length - 1; ri >= 0; ri--) {
        const ring = rings[ri];
        const progress = ring.r / ring.maxR;
        // Decelerate: rings start fast, slow to near-stop at edge
        const decel = ring.speed * Math.max(0.1, 1 - progress * 0.85);
        ring.r       += decel;
        ring.opacity -= 0.0085;

        if (ring.opacity <= 0 || ring.r > ring.maxR) {
          rings.splice(ri, 1);
          continue;
        }

        ctx.save();
        // Soft outer glow on ring
        ctx.shadowBlur  = 6;
        ctx.shadowColor = wc(WABAG.bright, ring.opacity * 0.6);
        ctx.strokeStyle = wc(WABAG.bright, ring.opacity);
        ctx.lineWidth   = ring.lineW;
        ctx.beginPath();
        // Ellipse: horizontal perspective for water surface
        ctx.ellipse(ring.x, ring.y, ring.r, ring.r * 0.32, 0, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }

      raf = requestAnimationFrame(tick);
    }

    raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
      window.removeEventListener('click', onClick);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position:      'fixed',
        top: 0, left: 0,
        width:         '100%',
        height:        '100%',
        pointerEvents: 'none',
        zIndex:        9999,
      }}
    />
  );
}
