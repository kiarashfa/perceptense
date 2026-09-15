/**
 * A rolodex: a ring of items turned by wheel, drag, swipe, arrow keys or its
 * buttons. Each item sits at offset `index - position`, wrapped into
 * (-n/2, n/2], so the ring has no ends. How an offset is drawn comes from a
 * place function, which is what makes one ring a card stack and another a list.
 */

export type Place = (item: HTMLElement, offset: number, width: number) => void;

interface Options {
  place: Place;
  horizontal: boolean;
  /** Pointer travel, in pixels, that turns the ring by one item. */
  dragPx: number;
  /** Let a vertical wheel turn a horizontal ring only over its front item. */
  wheelOnFrontOnly?: boolean;
  onFront?: (index: number) => void;
}

const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export function rolodex(wrap: HTMLElement, opts: Options): void {
  const el = wrap.querySelector<HTMLElement>('.rx');
  if (!el) return;
  const items = Array.from(el.querySelectorAll<HTMLElement>('.rx-item'));
  const n = items.length;
  if (n === 0) return;
  const countEl = wrap.querySelector<HTMLElement>('.rx-count b');

  let pos = 0;
  let target = 0;
  let raf = 0;
  let snapTimer = 0;
  let width = 0;
  let front = -1;

  const wrapOffset = (o: number) => {
    const m = ((o % n) + n) % n;
    return m > n / 2 ? m - n : m;
  };

  function render() {
    items.forEach((item, i) => {
      const o = wrapOffset(i - pos);
      opts.place(item, o, width);
      const isFront = Math.abs(o) < 0.5;
      if (item.dataset.front !== String(isFront)) {
        item.dataset.front = String(isFront);
        item.classList.toggle('is-front', isFront);
        item.tabIndex = isFront ? 0 : -1;
        item.setAttribute('aria-hidden', String(!isFront));
      }
    });
    const k = ((Math.round(pos) % n) + n) % n;
    if (k !== front) {
      front = k;
      if (countEl) countEl.textContent = String(k + 1).padStart(2, '0');
      opts.onFront?.(k);
    }
  }

  function tick() {
    const d = target - pos;
    if (still || Math.abs(d) < 0.002) {
      pos = target;
      raf = 0;
      render();
      return;
    }
    pos += d * 0.16;
    render();
    raf = requestAnimationFrame(tick);
  }

  function go(to: number) {
    target = to;
    if (!raf) raf = requestAnimationFrame(tick);
  }

  const step = (k: number) => go(Math.round(target) + k);

  el.addEventListener(
    'wheel',
    (e) => {
      const sideways = Math.abs(e.deltaX) > Math.abs(e.deltaY);
      let d: number;
      if (opts.horizontal) {
        if (sideways) d = e.deltaX;
        else if (e.shiftKey || !opts.wheelOnFrontOnly || (e.target as Element).closest('.rx-item.is-front')) d = e.deltaY;
        else return;
      } else {
        if (sideways) return;
        d = e.deltaY;
      }
      e.preventDefault();
      if (e.deltaMode === 1) d *= 33;
      go(target + d / 150);
      clearTimeout(snapTimer);
      snapTimer = window.setTimeout(() => go(Math.round(target)), 150);
    },
    { passive: false },
  );

  // Mouse drag and touch swipe share one path through pointer events. The
  // element's touch-action leaves the other axis to the page.
  let drag: { id: number; start: number; from: number; last: number; lastT: number; vel: number; active: boolean } | null = null;
  let swallowClick = false;
  const coord = (e: PointerEvent) => (opts.horizontal ? e.clientX : e.clientY);

  el.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    swallowClick = false;
    const p = coord(e);
    drag = { id: e.pointerId, start: p, from: target, last: p, lastT: e.timeStamp, vel: 0, active: false };
  });
  el.addEventListener('pointermove', (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const p = coord(e);
    const dist = p - drag.start;
    if (!drag.active) {
      if (Math.abs(dist) < 6) return;
      drag.active = true;
      el.setPointerCapture(e.pointerId);
      el.classList.add('is-dragging');
    }
    drag.vel = (p - drag.last) / Math.max(1, e.timeStamp - drag.lastT);
    drag.last = p;
    drag.lastT = e.timeStamp;
    cancelAnimationFrame(raf);
    raf = 0;
    target = pos = drag.from - dist / opts.dragPx;
    render();
  });
  const release = (e: PointerEvent) => {
    if (!drag || e.pointerId !== drag.id) return;
    if (drag.active) {
      swallowClick = true;
      el.classList.remove('is-dragging');
      go(Math.round(target - (drag.vel * 180) / opts.dragPx));
    }
    drag = null;
  };
  el.addEventListener('pointerup', release);
  el.addEventListener('pointercancel', release);
  el.addEventListener('dragstart', (e) => e.preventDefault());
  el.addEventListener(
    'click',
    (e) => {
      if (!swallowClick) return;
      swallowClick = false;
      e.preventDefault();
      e.stopPropagation();
    },
    true,
  );

  items.forEach((item, i) => {
    item.addEventListener('click', (e) => {
      const o = wrapOffset(i - target);
      if (Math.abs(o) >= 0.5) {
        e.preventDefault();
        go(Math.round(target + o));
      }
    });
  });

  el.addEventListener('keydown', (e) => {
    const next = opts.horizontal ? 'ArrowRight' : 'ArrowDown';
    const prev = opts.horizontal ? 'ArrowLeft' : 'ArrowUp';
    if (e.key === next) {
      e.preventDefault();
      step(1);
    } else if (e.key === prev) {
      e.preventDefault();
      step(-1);
    }
  });
  wrap.querySelectorAll<HTMLElement>('[data-step]').forEach((b) => {
    b.addEventListener('click', () => step(Number(b.dataset.step)));
  });

  const measure = () => {
    width = items[0].offsetWidth;
    render();
  };
  window.addEventListener('resize', measure);
  measure();
  el.classList.add('is-ready');
}

/** Cards side by side: the front one full size, neighbours smaller and dimmed. */
export const spotPlace: Place = (item, o, width) => {
  const a = Math.abs(o);
  if (a > 2.6) {
    item.style.visibility = 'hidden';
    return;
  }
  item.style.visibility = '';
  const x = Math.sign(o) * (Math.min(a, 1) * 0.66 + Math.max(0, a - 1) * 0.5) * width;
  item.style.transform = `translate(-50%, -50%) translateX(${x.toFixed(1)}px) scale(${(1 - a * 0.13).toFixed(3)})`;
  item.style.zIndex = String(100 - Math.round(a * 10));
  item.style.opacity = a <= 2 ? '1' : String(Math.max(0, (2.6 - a) / 0.6));
  item.style.setProperty('--dim', Math.min(0.72, a * 0.33).toFixed(3));
};

/** Rows stacked in a column, fading with distance from the front row. */
export function listPlace(rowHeight: number, visible = 2): Place {
  return (item, o) => {
    const a = Math.abs(o);
    if (a > visible + 0.9) {
      item.style.visibility = 'hidden';
      return;
    }
    item.style.visibility = '';
    item.style.transform = `translateY(${(o * rowHeight).toFixed(1)}px)`;
    item.style.opacity = String(Math.max(0, 1 - a * 0.34));
    item.style.zIndex = String(100 - Math.round(a * 10));
  };
}
