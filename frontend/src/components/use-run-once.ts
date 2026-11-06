import { useCallback, useRef, useState, type SyntheticEvent } from "react";

export interface RunOnce {
  /** An action is running, or all are done: what starts one shows it and stays disabled. */
  readonly busy: boolean;
  /**
   * Run ``action`` unless one is still running; a second call meanwhile does nothing and
   * gives undefined. The lock holds until the action has settled, also when it fails, and
   * already before the next render, so a double click or a repeated key cannot slip through.
   */
  readonly run: <T>(action: () => Promise<T>) => Promise<T | undefined>;
  /**
   * Run nothing more: the job is done, e.g. a dialog's form whose dialog is closing. Until
   * it is gone, a click or an Enter would otherwise do the same again.
   */
  readonly finish: () => void;
}

/** Let a user action (save, issue, send, print …) run once at a time. */
export function useRunOnce(): RunOnce {
  const running = useRef(false);
  const finished = useRef(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const run = useCallback(async <T>(action: () => Promise<T>): Promise<T | undefined> => {
    if (running.current || finished.current) return undefined;
    running.current = true;
    setBusy(true);
    try {
      return await action();
    } finally {
      running.current = false;
      setBusy(false);
    }
  }, []);
  const finish = useCallback(() => {
    finished.current = true;
    setDone(true);
  }, []);
  return { busy: busy || done, run, finish };
}

/**
 * Submit a form once at a time: ``handler`` is react-hook-form's ``handleSubmit(onValid)``.
 * Not its isSubmitting: a reset() inside the handler clears that while later steps still run.
 */
export function useSubmitOnce(handler: () => Promise<void>): {
  readonly busy: boolean;
  readonly submit: (event?: SyntheticEvent) => void;
  readonly finish: () => void;
} {
  const { busy, run, finish } = useRunOnce();
  return {
    busy,
    submit: (event) => {
      event?.preventDefault();
      void run(handler);
    },
    finish,
  };
}
