import { useEffect, useRef } from 'react';

type Drop = {
  x: number; y: number;
  r: number; speed: number;
  sway: number; phase: number; opacity: number;
};

type Ripple = {
  x: number; y: number;
  r: number; maxR: number; opacity: number;
  lineWidth: number; delay: number;
};

export default function WaterEffect() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener('resize', resize);

    /* ── Falling drops ─────────────────────────────── */
    const COUNT = 60;
    const drops: Drop[] = Array.from({ length: COUNT }, () => ({
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      r: Math.random() * 2.4 + 0.7,
      speed: Math.random() * 1.9 + 0.5,
      sway: (Math.random() - 0.5) * 0.28,
      phase: Math.random() * Math.PI * 2,
      opacity: Math.random() * 0.13 + 0.04,
    }));

    /* ── Click ripples ─────────────────────────────── */
    const ripples: Ripple[] = [];

    const spawnRipples = (x: number, y: number) => {
      [0, 80, 180].forEach((delay, i) => {
        ripples.push({
          x, y,
          r: 0,
          maxR: 70 + i * 38,
          opacity: 0.65 - i * 0.12,
          lineWidth: 1.8 - i * 0.35,
          delay,
        });
      });
    };

    const handleClick = (e: MouseEvent) => spawnRipples(e.clientX, e.clientY);
    window.addEventListener('click', handleClick);

    let frame = 0;
    let raf: number;
    let elapsed = 0;
    let last = performance.now();

    function draw(now: number) {
      const dt = now - last;
      last = now;
      elapsed += dt;
      frame++;

      ctx!.clearRect(0, 0, canvas!.width, canvas!.height);

      /* ── Draw drops ── */
      drops.forEach(d => {
        d.y += d.speed;
        d.x += Math.sin(frame * 0.013 + d.phase) * 0.28 + d.sway;

        if (d.y > canvas!.height + 20) {
          d.y = -20;
          d.x = Math.random() * canvas!.width;
          d.opacity = Math.random() * 0.13 + 0.04;
          d.speed = Math.random() * 1.9 + 0.5;
        }
        if (d.x < -10) d.x = canvas!.width + 5;
        if (d.x > canvas!.width + 10) d.x = -5;

        ctx!.save();
        ctx!.translate(d.x, d.y);
        ctx!.fillStyle = `rgba(96,165,250,${d.opacity})`;

        /* teardrop path */
        ctx!.beginPath();
        ctx!.moveTo(0, -d.r * 2.6);
        ctx!.bezierCurveTo(
           d.r * 1.15, -d.r * 0.9,
           d.r * 1.15,  d.r * 0.75,
           0,           d.r * 1.3,
        );
        ctx!.bezierCurveTo(
          -d.r * 1.15,  d.r * 0.75,
          -d.r * 1.15, -d.r * 0.9,
          0,            -d.r * 2.6,
        );
        ctx!.fill();

        /* subtle highlight */
        ctx!.fillStyle = `rgba(147,197,253,${d.opacity * 0.45})`;
        ctx!.beginPath();
        ctx!.ellipse(-d.r * 0.3, -d.r * 1.4, d.r * 0.22, d.r * 0.42, -0.4, 0, Math.PI * 2);
        ctx!.fill();

        ctx!.restore();
      });

      /* ── Draw ripples ── */
      for (let i = ripples.length - 1; i >= 0; i--) {
        const rip = ripples[i];
        if (elapsed < rip.delay) continue;

        rip.r += 2.8;
        rip.opacity -= 0.016;

        if (rip.opacity <= 0 || rip.r > rip.maxR) {
          ripples.splice(i, 1);
          continue;
        }

        /* outer ring */
        ctx!.save();
        ctx!.strokeStyle = `rgba(96,165,250,${rip.opacity})`;
        ctx!.lineWidth = rip.lineWidth;
        ctx!.beginPath();
        ctx!.ellipse(rip.x, rip.y, rip.r, rip.r * 0.38, 0, 0, Math.PI * 2);
        ctx!.stroke();

        /* inner fill shimmer */
        if (rip.r < 30) {
          ctx!.fillStyle = `rgba(59,130,246,${rip.opacity * 0.08})`;
          ctx!.beginPath();
          ctx!.ellipse(rip.x, rip.y, rip.r, rip.r * 0.38, 0, 0, Math.PI * 2);
          ctx!.fill();
        }
        ctx!.restore();
      }

      raf = requestAnimationFrame(draw);
    }

    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
      window.removeEventListener('click', handleClick);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed',
        top: 0, left: 0,
        width: '100%', height: '100%',
        pointerEvents: 'none',
        zIndex: 9999,
      }}
    />
  );
}
