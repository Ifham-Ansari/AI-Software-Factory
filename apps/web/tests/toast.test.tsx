import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider, useToast, type ToastVariant } from "@/components/ui";

/**
 * Toast notifications [F-217].
 *
 * The behaviours worth pinning down are the ones that decide whether a user misses
 * something: that errors do not vanish on their own, that hovering stops the clock, and
 * that the live region exists before anything is announced into it.
 */

/** A button that raises a toast, so tests drive the provider the way the app does. */
function Raise({
  message,
  variant,
  duration,
}: {
  message: string;
  variant?: ToastVariant;
  duration?: number;
}) {
  const { notify } = useToast();
  return (
    <button type="button" onClick={() => notify(message, { variant, duration })}>
      raise
    </button>
  );
}

function renderWith(ui: React.ReactNode) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

describe("ToastProvider", () => {
  it("announces into a live region that already exists", () => {
    // A live region created at the same moment as its first message is usually not
    // announced at all: assistive technology only reports changes to a region it was
    // already observing.
    renderWith(<Raise message="hello" />);

    const region = screen.getByTestId("toast-viewport").querySelector("[aria-live]");
    expect(region).toBeInTheDocument();
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(screen.queryAllByTestId("toast")).toHaveLength(0);
  });

  it("shows a toast when one is raised", async () => {
    const user = userEvent.setup();
    renderWith(<Raise message="Project created." variant="success" />);

    await user.click(screen.getByRole("button", { name: "raise" }));

    expect(screen.getByText("Project created.")).toBeInTheDocument();
  });

  it("gives an error the assertive role so it interrupts", async () => {
    const user = userEvent.setup();
    renderWith(<Raise message="Could not delete." variant="error" />);

    await user.click(screen.getByRole("button", { name: "raise" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Could not delete.");
  });

  it("can be dismissed by hand", async () => {
    const user = userEvent.setup();
    renderWith(<Raise message="Saved." variant="success" />);
    await user.click(screen.getByRole("button", { name: "raise" }));

    await user.click(screen.getByRole("button", { name: "Dismiss notification" }));

    expect(screen.queryByText("Saved.")).not.toBeInTheDocument();
  });

  it("throws when used outside the provider", () => {
    // Silently doing nothing would hide the failure in exactly the situation the toast
    // was meant to cover.
    const quiet = vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => render(<Raise message="x" />)).toThrow(/ToastProvider/);
    quiet.mockRestore();
  });
});

describe("dismissal timing", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  /**
   * `fireEvent`, not `userEvent`, throughout this block.
   *
   * userEvent inserts its own asynchronous delays between the events it synthesises, and
   * under fake timers nothing advances those delays, so a click never completes and the
   * test times out. These cases are about when a toast disappears, not about faithfully
   * reproducing pointer input, so dispatching the event directly is both sufficient and
   * the only thing that composes with a frozen clock.
   */
  const raiseToast = () => {
    fireEvent.click(screen.getByRole("button", { name: "raise" }));
  };

  const advance = async (ms: number) => {
    await act(async () => {
      vi.advanceTimersByTime(ms);
    });
  };

  it("dismisses a success automatically", async () => {
    renderWith(<Raise message="Saved." variant="success" />);
    raiseToast();
    expect(screen.getByText("Saved.")).toBeInTheDocument();

    await advance(5_000);

    expect(screen.queryByText("Saved.")).not.toBeInTheDocument();
  });

  it("keeps an error until it is dismissed", async () => {
    // The one that matters. "Your project was not deleted" disappearing on a timer is how
    // a user comes to believe the opposite.
    renderWith(<Raise message="Could not delete." variant="error" />);
    raiseToast();

    await advance(60_000);

    expect(screen.getByText("Could not delete.")).toBeInTheDocument();
  });

  it("stops the clock while hovered, and resumes where it left off", async () => {
    renderWith(<Raise message="Saved." variant="success" duration={1_000} />);
    raiseToast();

    await advance(600);
    fireEvent.mouseEnter(screen.getByTestId("toast"));
    await advance(10_000);
    expect(screen.getByText("Saved.")).toBeInTheDocument();

    fireEvent.mouseLeave(screen.getByTestId("toast"));
    // 400ms of the original second remained; resuming must not restart the full duration,
    // so 500ms is enough to finish it and 300ms would not be.
    await advance(300);
    expect(screen.getByText("Saved.")).toBeInTheDocument();
    await advance(200);

    expect(screen.queryByText("Saved.")).not.toBeInTheDocument();
  });

  it("keeps only the most recent few", async () => {
    renderWith(<Raise message="Saved." variant="error" />);

    for (let i = 0; i < 6; i++) raiseToast();

    const viewport = screen.getByTestId("toast-viewport");
    expect(within(viewport).getAllByTestId("toast")).toHaveLength(4);
  });
});
