import { useEffect, useState } from "react";
import choiceArrow from "../assets/ui/choice-arrow.svg";
import loadingDots from "../assets/ui/loading-dots.svg";

export function ChoiceButton({
  letter,
  text,
  hint,
  disabled,
  onClick,
}: {
  letter: string;
  text: string;
  hint?: string;
  disabled: boolean;
  onClick: () => void;
}) {
  const [loading, setLoading] = useState(false);
  // When the turn resolves the parent clears `busy` (disabled flips back to
  // false); drop the spinner then so the arrow returns without a layout shift.
  useEffect(() => {
    if (!disabled) setLoading(false);
  }, [disabled]);
  return (
    <button
      className={`choice-button choice-${letter.toLowerCase()}${loading ? " is-loading" : ""}`}
      disabled={disabled || loading}
      title={hint}
      aria-label={`${letter}：${text}`}
      aria-busy={loading}
      onClick={() => {
        setLoading(true);
        onClick();
      }}
    >
      <span className="choice-mark">{letter}</span>
      <span className="choice-copy">
        <em>{text}</em>
      </span>
      {loading ? (
        <img className="choice-spinner" src={loadingDots} alt="" aria-hidden="true" />
      ) : (
        <img className="choice-arrow" src={choiceArrow} alt="" aria-hidden="true" />
      )}
    </button>
  );
}
