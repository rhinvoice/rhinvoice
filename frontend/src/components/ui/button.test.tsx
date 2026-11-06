import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";

function deferred() {
  let resolve: () => void = () => undefined;
  let reject: () => void = () => undefined;
  const promise = new Promise<void>((done, fail) => {
    resolve = done;
    reject = () => {
      fail(new Error("refused"));
    };
  });
  return { promise, resolve, reject };
}

describe("Button", () => {
  it("runs what it starts once, shows that it works, and unlocks when it is done", async () => {
    const action = deferred();
    const onClick = vi.fn(() => action.promise);
    render(<Button onClick={onClick}>Ausstellen</Button>);
    const button = screen.getByRole("button", { name: "Ausstellen" });
    act(() => {
      fireEvent.click(button);
      fireEvent.click(button);
    });
    expect(onClick).toHaveBeenCalledOnce();
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button.querySelector("[data-spinner]")).not.toBeNull();
    await act(async () => {
      action.resolve();
      await action.promise;
    });
    expect(button).toBeEnabled();
    expect(button.querySelector("[data-spinner]")).toBeNull();
  });

  it("unlocks when the action fails, which reports the failure itself", async () => {
    const action = deferred();
    const onClick = vi.fn(() => action.promise);
    render(<Button onClick={onClick}>Senden</Button>);
    const button = screen.getByRole("button", { name: "Senden" });
    act(() => {
      fireEvent.click(button);
    });
    await act(async () => {
      action.reject();
      await action.promise.catch(() => undefined);
    });
    expect(button).toBeEnabled();
    act(() => {
      fireEvent.click(button);
    });
    expect(onClick).toHaveBeenCalledTimes(2);
  });

  it("renders a link in its place, with the link's own content", () => {
    render(
      <Button asChild>
        <a href="/invoices/new">Neue Rechnung</a>
      </Button>,
    );
    const link = screen.getByRole("link", { name: "Neue Rechnung" });
    expect(link).toHaveAttribute("href", "/invoices/new");
    expect(link).toHaveAttribute("data-slot", "button");
    expect(link).not.toHaveAttribute("disabled");
  });

  it("shows what its form is doing", () => {
    render(
      <Button type="submit" busy>
        Speichern
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Speichern" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });
});

describe("AlertDialogAction", () => {
  it("acts once per opening, also while the dialog closes", () => {
    const onClick = vi.fn();
    render(
      <AlertDialog open>
        <AlertDialogContent>
          <AlertDialogTitle>Rechnung stornieren?</AlertDialogTitle>
          <AlertDialogDescription>Das lässt sich nicht rückgängig machen.</AlertDialogDescription>
          <AlertDialogAction onClick={onClick}>Stornieren</AlertDialogAction>
        </AlertDialogContent>
      </AlertDialog>,
    );
    const action = screen.getByRole("button", { name: "Stornieren" });
    act(() => {
      fireEvent.click(action);
      fireEvent.click(action);
    });
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("may act again when it kept the dialog open, once its work is done", async () => {
    const work = deferred();
    const onClick = vi.fn((event: { preventDefault: () => void }) => {
      event.preventDefault();
      return work.promise;
    });
    render(
      <AlertDialog open>
        <AlertDialogContent>
          <AlertDialogTitle>Vorlage löschen?</AlertDialogTitle>
          <AlertDialogDescription>Sie wird entfernt.</AlertDialogDescription>
          <AlertDialogAction onClick={onClick}>Löschen</AlertDialogAction>
        </AlertDialogContent>
      </AlertDialog>,
    );
    const action = screen.getByRole("button", { name: "Löschen" });
    act(() => {
      fireEvent.click(action);
      fireEvent.click(action);
    });
    expect(onClick).toHaveBeenCalledOnce();
    await act(async () => {
      work.resolve();
      await work.promise;
    });
    act(() => {
      fireEvent.click(action);
    });
    expect(onClick).toHaveBeenCalledTimes(2);
  });
});
