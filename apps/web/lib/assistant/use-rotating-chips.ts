"use client";

import { useEffect, useRef, useState } from "react";

/**
 * The rotating strip of "things to ask" used by the floating assistant. Shows a random few
 * of a pool and reshuffles them every several seconds while `active`, so the surface always
 * suggests something without listing everything. Rotation
 * holds while the pointer or keyboard focus is inside the strip, so a chip is never pulled
 * out from under a click, and stops entirely once `active` goes false (the person has said
 * something, or the surface closed).
 *
 * `pool` must be a stable reference - a module-level constant, or a value from state/props -
 * because a fresh array on every render would reshuffle on every render.
 */

const VISIBLE = 3;
const CYCLE_MS = 6000;
const EMPTY_POOL: readonly string[] = [];

function shuffled(pool: readonly string[]): string[] {
  const copy = [...pool];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

function sample(pool: readonly string[], companionPool: readonly string[]): string[] {
  if (companionPool.length === 0) return shuffled(pool).slice(0, VISIBLE);

  // A contextual surface can reserve one chip for the assistant's broader capabilities.
  // Deduplicate in case the two pools ever acquire the same wording.
  const contextual = shuffled(pool).slice(0, VISIBLE - 1);
  const companion = shuffled(companionPool).find((item) => !contextual.includes(item));
  return shuffled(companion ? [...contextual, companion] : contextual);
}

export function useRotatingChips(pool: readonly string[], active: boolean, companionPool: readonly string[] = EMPTY_POOL) {
  const [chips, setChips] = useState<string[]>([]);
  // Bumped on every reshuffle so the caller can key the buttons off it and replay the
  // entrance animation.
  const [cycle, setCycle] = useState(0);
  const paused = useRef(false);

  useEffect(() => {
    if (!active || pool.length === 0) {
      setChips([]);
      return;
    }

    setChips(sample(pool, companionPool));
    setCycle((n) => n + 1);

    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion || pool.length <= VISIBLE) return;

    const timer = window.setInterval(() => {
      if (paused.current) return;
      setChips(sample(pool, companionPool));
      setCycle((n) => n + 1);
    }, CYCLE_MS);
    return () => window.clearInterval(timer);
  }, [pool, companionPool, active]);

  const holdHandlers = {
    onMouseEnter: () => {
      paused.current = true;
    },
    onMouseLeave: () => {
      paused.current = false;
    },
    onFocusCapture: () => {
      paused.current = true;
    },
    onBlurCapture: () => {
      paused.current = false;
    }
  };

  return { chips, cycle, holdHandlers };
}
