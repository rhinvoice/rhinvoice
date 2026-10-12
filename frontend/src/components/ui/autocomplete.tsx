import { useEffect, useId, useState, type KeyboardEvent, type ReactNode, type Ref } from "react";

import { fieldClasses } from "@/components/ui/field-styles";
import { cn } from "@/lib/cn";

interface AutocompleteProps<T> {
  readonly value: string;
  readonly onValueChange: (value: string) => void;
  readonly options: readonly T[];
  readonly optionKey: (option: T) => string;
  readonly renderOption: (option: T) => ReactNode;
  readonly onSelect: (option: T) => void;
  /** Accessible name of the suggestion list, e.g. "Customers". */
  readonly listLabel: string;
  /** Announced to screen readers while the list is open, e.g. "3 results". */
  readonly countLabel?: (count: number) => string;
  /** Shown when the list is open but has no options, e.g. "No customers found". */
  readonly emptyText?: string;
  /** Open the list only from this many characters on (0: also on focus). */
  readonly minLength?: number;
  readonly onBlur?: () => void;
  readonly onKeyDown?: (event: KeyboardEvent<HTMLInputElement>) => void;
  readonly ref?: Ref<HTMLInputElement>;
  readonly id?: string | undefined;
  readonly name?: string;
  readonly placeholder?: string;
  readonly className?: string;
  readonly inputClassName?: string;
  readonly "aria-describedby"?: string | undefined;
  readonly "aria-invalid"?: boolean | undefined;
  readonly "aria-label"?: string;
}

/**
 * Text input with a list of suggestions (WAI-ARIA combobox pattern with
 * aria-activedescendant): ↓/↑ move through the list, ↵ picks, Esc closes.
 * Typing stays free text; picking an option is optional.
 */
export function Autocomplete<T>({
  value,
  onValueChange,
  options,
  optionKey,
  renderOption,
  onSelect,
  listLabel,
  countLabel,
  emptyText,
  minLength = 1,
  onBlur,
  onKeyDown: onOtherKeyDown,
  ref,
  id,
  name,
  placeholder,
  className,
  inputClassName,
  ...aria
}: AutocompleteProps<T>) {
  const generated = useId();
  const inputId = id ?? generated;
  const listId = `${inputId}-options`;
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const enoughText = value.trim().length >= minLength;
  const showList = open && enoughText && (options.length > 0 || emptyText !== undefined);
  const activeOption = showList ? options[active] : undefined;
  const activeId = activeOption === undefined ? undefined : `${listId}-${optionKey(activeOption)}`;

  // Keep the option chosen with the keyboard visible in the scrolling list.
  useEffect(() => {
    if (activeId !== undefined) {
      document.getElementById(activeId)?.scrollIntoView({ block: "nearest" });
    }
  }, [activeId]);

  const pick = (option: T) => {
    onSelect(option);
    setOpen(false);
    setActive(-1);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    // Alt+arrows are left to the caller (e.g. reordering lines).
    if (!event.altKey && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        setActive(event.key === "ArrowDown" ? 0 : options.length - 1);
        return;
      }
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((current) =>
        options.length === 0 ? -1 : (current + step + options.length) % options.length,
      );
    } else if (event.key === "Enter" && activeOption !== undefined) {
      event.preventDefault();
      pick(activeOption);
    } else if (event.key === "Escape" && showList) {
      // Only consume Escape while the list is open, so dialogs still close.
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
      setActive(-1);
    } else {
      onOtherKeyDown?.(event);
    }
  };

  return (
    <div className={cn("relative", className)}>
      <input
        ref={ref}
        id={inputId}
        name={name}
        type="text"
        role="combobox"
        autoComplete="off"
        aria-autocomplete="list"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={activeId}
        placeholder={placeholder}
        value={value}
        onChange={(event) => {
          onValueChange(event.target.value);
          setOpen(true);
          setActive(-1);
        }}
        onFocus={() => {
          if (minLength === 0) setOpen(true);
        }}
        onBlur={() => {
          setOpen(false);
          setActive(-1);
          onBlur?.();
        }}
        onKeyDown={onKeyDown}
        className={cn(
          fieldClasses,
          "flex h-10 px-3 py-1",
          "aria-invalid:border-destructive",
          inputClassName,
        )}
        {...aria}
      />
      {countLabel === undefined ? null : (
        <span className="sr-only" aria-live="polite">
          {showList ? countLabel(options.length) : ""}
        </span>
      )}
      <div
        id={listId}
        role="listbox"
        aria-label={listLabel}
        hidden={!showList}
        className="absolute inset-x-0 top-full z-50 mt-1 max-h-72 min-w-64 overflow-y-auto rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
      >
        {options.length === 0 ? (
          <p className="px-2 py-2 text-sm text-muted-foreground">{emptyText}</p>
        ) : (
          options.map((option, index) => (
            <div
              key={optionKey(option)}
              id={`${listId}-${optionKey(option)}`}
              role="option"
              tabIndex={-1}
              aria-selected={index === active}
              // Keep the focus in the input; the click still selects.
              onMouseDown={(event) => {
                event.preventDefault();
              }}
              onClick={() => {
                pick(option);
              }}
              // Options are not tab stops; this only covers a programmatically focused option.
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  pick(option);
                }
              }}
              className={cn(
                "flex min-h-9 cursor-pointer flex-col justify-center rounded-sm px-2 py-1.5 text-sm",
                index === active ? "bg-accent text-accent-foreground" : "hover:bg-muted",
              )}
            >
              {renderOption(option)}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
