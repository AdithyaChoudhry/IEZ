import { useEffect, useRef } from 'react';

/**
 * Scroll reveal: elements with class "reveal" fade and rise into place the first time they enter the viewport.
 * Usage: const ref = useReveal<HTMLDivElement>();  <div ref={ref}> ... <section className="reveal" style={{'--d':'80ms'}}> ...
 * Falls back to showing everything at once when IntersectionObserver is unavailable.
 */
export function useReveal<T extends HTMLElement>(): React.RefObject<T> {
  const ref = useRef<T>(null);
  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    const items = Array.from(root.querySelectorAll<HTMLElement>('.reveal'));
    if (typeof IntersectionObserver === 'undefined') { items.forEach((el) => el.classList.add('in')); return; }
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
    }, { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });
    items.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);
  return ref;
}
