import { useEffect, useRef, type MouseEvent } from "react";

/**
 * Basic modal/dialog a11y: focus the first interactive element on open, restore
 * focus to the trigger on close, close on Escape, and close when the scrim
 * (overlay) itself is clicked. Returns a ref for the scrim element and an
 * onClick handler to attach to it.
 */
export function useDialogA11y(onClose: () => void) {
  const scrimRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const focusable = scrimRef.current?.querySelector<HTMLElement>(
      "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])"
    );
    focusable?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus?.();
    };
  }, []);

  const onScrimClick = (e: MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onCloseRef.current();
  };

  return { scrimRef, onScrimClick };
}
