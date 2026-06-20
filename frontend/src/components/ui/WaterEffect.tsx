import { useEffect, useRef } from 'react';

/* ─────────────────────────────────────────────────────────────────────────────
   WATER EFFECT  —  CEO-Grade Premium Animation
   Three-depth-layer rainfall + gravity acceleration + speed-elongation +
   dual-highlight shimmer + bottom-splash particles + multi-ring click ripples
───────────────────────────────────────────────────────────────────────────── */

type Layer = 'far' | 'mid' | 'near';

type Drop = {
  x: number; y: number;
  r: number;           // base radius
  vy: number;          // current vertical speed
  vx: number;          // subtle horizontal drift
  phase: number;       // sway phase offset
  opacity: number;
  layer: Layer;
  trail: { x: number; y: number; o: number }[];
};

type Splash = {
  x: number; y: number;
  particles: { vx: number; vy: number; r: number; life: number }[];
};

type Ripple = {
  x: number; y: number;
  rings: { r: number; maxR: number; opacity: number; speed: number; lineWidth: number }[];
  splashPts: { angle: number; dist: number; opacity: number; r: number }[];
};

/* Layer config: far = tiny + very faint, near = larger + faster + more visible */
const LAYER: Record<Layer, { rMin: number; rMax: number; sMin: number; sMax: number; oMin: number; oMax: number; count: number }> = {
  far:  { rMin: 0.6, rMax: 1.1, sMin: 0.5,  sMax: 1.1,  oMin: 0.03, oMax: 0.08, count: 18 },
  mid:  { rMin: 1.2, rMax: 2.0, sMin: 1.0,  sMax: 2.0,  oMin: 0.06, oMax: 0.13, count: 14 },
  near: { rMin: 2.1, rMax: 3.2, sMin: 1.8,  sMax: 3.2,  oMin: 0.09, oMax: 0.18, count: 8  },
};

function makeDrop(layer: Layer, w: number, h: number, randomY = true): Drop {
  const lc = LAYER[layer];
  const r  = lc.rMin + Math.random() * (lc.rMax - lc.rMin);
  return {
    x: Math.random() * w,
    y: randomY ? Math.random() * h : -(r * 5 + Math.random() * 60),
    r,
    vy: lc.sMin + Math.random() * (lc.sMax - lc.sMin),
    vx: (Math.random() - 0.5) * 0.18,
    phase: Math.random() * Math.PI * 2,
    opacity: lc.oMin + Math.random() * (lc.oMax - lc.oMin),
    layer,
    trail: [],
  };
}

function drawDrop(ctx: CanvasRenderingContext2D, d: Drop) {
  const speed   = Math.abs(d.vy);
  const stretch = 1 + speed * 0.35;         // elongate with speed
  const rw      = d.r;                      // horizontal radius
  const rh      = d.r * stretch;            // vertical radius (stretched)

  ctx.save();
  ctx.translate(d.x, d.y);

  /* ── Trailing streak ── */
  if (speed > 1.5 && d.trail.length > 0) {
    d.trail.forEach((pt, i) => {
      const alpha = pt.o * (i / d.trail.length) * 0.45;
      ctx.beginPath();
      ctx.ellipse(pt.x - d.x, pt.y - d.y, rw * 0.55, rh * 0.28, 0, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(96,165,250,${alpha})`;
      ctx.fill();
    });
  }

  /* ── Ambient outer glow ── */
  const grd = ctx.createRadialGradient(0, rh * 0.2, 0, 0, 0, rh * 2.2);
  grd.addColorStop(0,   `rgba(59,130,246,${d.opacity * 0.18})`);
  grd.addColorStop(1,   'rgba(59,130,246,0)');
  ctx.beginPath();
  ctx.ellipse(0, 0, rw * 2.2, rh * 2.2, 0, 0, Math.PI * 2);
  ctx.fillStyle = grd;
  ctx.fill();

  /* ── Drop body — premium teardrop ── */
  const body = ctx.createRadialGradient(-rw * 0.22, -rh * 0.3, 0, 0, 0, rh * 1.4);
  body.addColorStop(0,   `rgba(147,197,253,${d.opacity * 1.4})`);
  body.addColorStop(0.45,`rgba(96,165,250,${d.opacity * 1.1})`);
  body.addColorStop(0.78,`rgba(37,99,235,${d.opacity})`);
  body.addColorStop(1,   `rgba(29,78,216,${d.opacity * 0.7})`);

  ctx.beginPath();
  ctx.moveTo(0, -rh * 2.4);
  ctx.bezierCurveTo( rw * 1.1, -rh * 0.85,  rw * 1.1,  rh * 0.8,  0,  rh * 1.25);
  ctx.bezierCurveTo(-rw * 1.1,  rh * 0.8, -rw * 1.1, -rh * 0.85,  0, -rh * 2.4);
  ctx.fillStyle = body;
  ctx.fill();

  /* ── Primary highlight (bright crescent, top-left) ── */
  ctx.save();
  ctx.clip();  // clip to drop shape (re-use path above — rebuild)
  ctx.beginPath();
  ctx.moveTo(0, -rh * 2.4);
  ctx.bezierCurveTo( rw * 1.1, -rh * 0.85,  rw * 1.1,  rh * 0.8,  0,  rh * 1.25);
  ctx.bezierCurveTo(-rw * 1.1,  rh * 0.8, -rw * 1.1, -rh * 0.85,  0, -rh * 2.4);

  const h1 = ctx.createRadialGradient(-rw * 0.3, -rh * 1.5, 0, -rw * 0.3, -rh * 1.5, rh * 0.85);
  h1.addColorStop(0,   `rgba(255,255,255,${d.opacity * 1.2})`);
  h1.addColorStop(0.5, `rgba(219,234,254,${d.opacity * 0.4})`);
  h1.addColorStop(1,   'rgba(219,234,254,0)');
  ctx.fillStyle = h1;
  ctx.fill();

  /* ── Secondary micro-highlight (tiny spark) ── */
  const h2 = ctx.createRadialGradient(-rw * 0.55, -rh * 1.85, 0, -rw * 0.55, -rh * 1.85, rw * 0.28);
  h2.addColorStop(0,   `rgba(255,255,255,${d.opacity * 0.95})`);
  h2.addColorStop(1,   'rgba(255,255,255,0)');
  ctx.fillStyle = h2;
  ctx.fill();

  ctx.restore();

  /* ── Refraction edge ── */
  ctx.beginPath();
  ctx.moveTo(0, -rh * 2.4);
  ctx.bezierCurveTo( rw * 1.1, -rh * 0.85,  rw * 1.1,  rh * 0.8,  0,  rh * 1.25);
  ctx.bezierCurveTo(-rw * 1.1,  rh * 0.8, -rw * 1.1, -rh * 0.85,  0, -rh * 2.4);
  ctx.strokeStyle = `rgba(147,197,253,${d.opacity * 0.35})`;
  ctx.lineWidth = 0.5;
  ctx.stroke();

  ctx.restore();
}

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

    /* ── Populate drops for each layer ── */
    const drops: Drop[] = [];
    (['far', 'mid', 'near'] as Layer[]).forEach(layer => {
      for (let i = 0; i < LAYER[layer].count; i++) drops.push(makeDrop(layer, w, h, true));
    });

    /* ── Sort so far renders first (behind) ── */
    const ORDER: Record<Layer, number> = { far: 0, mid: 1, near: 2 };
    drops.sort((a, b) => ORDER[a.layer] - ORDER[b.layer]);

    /* ── Splash pool ── */
    const splashes: Splash[] = [];

    /* ── Click ripple pool ── */
    const ripples: Ripple[] = [];

    const spawnRipple = (x: number, y: number) => {
      const pts = Array.from({ length: 8 }, (_, i) => ({
        angle:   (Math.PI * 2 * i) / 8,
        dist:    0,
        opacity: 0.7,
        r:       1.2 + Math.random() * 1.0,
      }));

      ripples.push({
        x, y,
        splashPts: pts,
        rings: [
          { r: 0, maxR: 48,  opacity: 0.75, speed: 3.8, lineWidth: 2.0 },
          { r: 0, maxR: 88,  opacity: 0.50, speed: 3.2, lineWidth: 1.4 },
          { r: 0, maxR: 130, opacity: 0.32, speed: 2.6, lineWidth: 1.0 },
          { r: 0, maxR: 175, opacity: 0.18, speed: 2.0, lineWidth: 0.7 },
        ],
      });
    };

    const onClick = (e: MouseEvent) => spawnRipple(e.clientX, e.clientY);
    window.addEventListener('click', onClick);

    let frame = 0;
    let raf: number;

    function tick() {
      ctx.clearRect(0, 0, w, h);
      frame++;

      /* ── Gravity constant ── */
      const GRAVITY = 0.018;

      /* ── Update + draw drops ── */
      drops.forEach(d => {
        /* trail history */
        d.trail.push({ x: d.x, y: d.y, o: d.opacity });
        if (d.trail.length > 6) d.trail.shift();

        /* physics: gravity accelerates, gentle sway */
        d.vy += GRAVITY;
        d.x  += d.vx + Math.sin(frame * 0.012 + d.phase) * 0.22;
        d.y  += d.vy;

        /* clamp sway */
        if (d.x < -20) d.x = w + 10;
        if (d.x > w + 20) d.x = -10;

        /* hit bottom → spawn splash → reset */
        if (d.y > h + d.r * 3) {
          /* splash only for mid/near */
          if (d.layer !== 'far' && Math.random() < 0.7) {
            splashes.push({
              x: d.x,
              y: h - 2,
              particles: Array.from({ length: 5 + Math.floor(Math.random() * 4) }, () => ({
                vx:   (Math.random() - 0.5) * 2.4,
                vy:   -(Math.random() * 1.8 + 0.6),
                r:    0.4 + Math.random() * 0.8,
                life: 1.0,
              })),
            });
          }
          const reset = makeDrop(d.layer, w, h, false);
          Object.assign(d, reset);
          d.trail = [];
        }

        drawDrop(ctx, d);
      });

      /* ── Splash particles ── */
      for (let si = splashes.length - 1; si >= 0; si--) {
        const sp = splashes[si];
        let alive = false;
        sp.particles.forEach(p => {
          if (p.life <= 0) return;
          p.life -= 0.045;
          p.vx   *= 0.94;
          p.vy   += 0.12;
          sp.x   += p.vx;
          sp.y   += p.vy;
          alive   = true;

          ctx.beginPath();
          ctx.arc(sp.x, sp.y, p.r, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(96,165,250,${p.life * 0.22})`;
          ctx.fill();
        });
        if (!alive) splashes.splice(si, 1);
      }

      /* ── Click ripples ── */
      for (let ri = ripples.length - 1; ri >= 0; ri--) {
        const rip = ripples[ri];
        let alive = false;

        /* rings */
        rip.rings.forEach(ring => {
          if (ring.opacity <= 0) return;
          ring.r       += ring.speed;
          ring.opacity -= 0.012;
          if (ring.opacity < 0) ring.opacity = 0;
          alive = true;

          /* elliptical ring — perspective (wider than tall) */
          ctx.save();
          ctx.strokeStyle = `rgba(96,165,250,${ring.opacity})`;
          ctx.lineWidth   = ring.lineWidth;
          ctx.shadowBlur  = 4;
          ctx.shadowColor = `rgba(59,130,246,${ring.opacity * 0.5})`;
          ctx.beginPath();
          ctx.ellipse(rip.x, rip.y, ring.r, ring.r * 0.36, 0, 0, Math.PI * 2);
          ctx.stroke();
          ctx.restore();
        });

        /* centre splash dots */
        rip.splashPts.forEach(pt => {
          if (pt.opacity <= 0) return;
          pt.dist    += 2.8;
          pt.opacity -= 0.05;
          alive       = true;
          const px = rip.x + Math.cos(pt.angle) * pt.dist;
          const py = rip.y + Math.sin(pt.angle) * pt.dist * 0.38;
          ctx.beginPath();
          ctx.arc(px, py, pt.r * pt.opacity, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(147,197,253,${pt.opacity * 0.75})`;
          ctx.fill();
        });

        if (!alive) ripples.splice(ri, 1);
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
        top:           0,
        left:          0,
        width:         '100%',
        height:        '100%',
        pointerEvents: 'none',
        zIndex:        9999,
      }}
    />
  );
}
