import { ChevronRight } from "lucide-react";

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
  return (
    <button className={`choice-button choice-${letter.toLowerCase()}`} disabled={disabled} title={hint} aria-label={`${letter}：${text}`} onClick={onClick}>
      <span className="choice-mark">{letter}</span>
      <span className="choice-copy">
        <em>{text}</em>
      </span>
      <ChevronRight size={20} aria-hidden="true" />
    </button>
  );
}
