import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ConfirmDialog, Modal } from "@/components/ui";

/**
 * Modal dialogs and destructive confirmation [F-218].
 *
 * These assert the parts that are ours: that React state stays the source of truth for
 * whether the dialog is open, that Escape and the backdrop route back through `onClose`,
 * and that focus lands on the safe action rather than the destructive one.
 *
 * They deliberately do not assert focus containment or the inert background. Those come
 * from the browser's `<dialog>` implementation, jsdom does not have them, and a test
 * against the setup polyfill would only be checking the polyfill. The Playwright suite
 * covers them where they are real.
 */

describe("Modal", () => {
  it("is hidden from the accessibility tree when closed", () => {
    // Queried by role rather than by node: a closed <dialog> is still in the DOM, and what
    // matters is that its contents are unreachable — not merely invisible. `queryByRole`
    // returns null for anything hidden, which is the property being asserted.
    render(<Modal open={false} onClose={vi.fn()} title="Settings" />);

    expect(screen.queryByRole("heading", { name: "Settings" })).toBeNull();
  });

  it("opens when asked", () => {
    render(<Modal open onClose={vi.fn()} title="Settings" />);

    expect(screen.getByRole("heading", { name: "Settings" }).closest("dialog")).toHaveAttribute(
      "open",
    );
  });

  it("labels itself with its title for assistive technology", () => {
    render(<Modal open onClose={vi.fn()} title="Delete project" description="Cannot be undone." />);

    const dialog = screen.getByRole("heading", { name: "Delete project" }).closest("dialog");
    const labelId = dialog?.getAttribute("aria-labelledby");
    const describedId = dialog?.getAttribute("aria-describedby");
    expect(document.getElementById(labelId ?? "")).toHaveTextContent("Delete project");
    expect(document.getElementById(describedId ?? "")).toHaveTextContent("Cannot be undone.");
  });

  it("routes Escape back through onClose instead of closing itself", () => {
    // The browser would otherwise close the dialog behind React's back, leaving `open`
    // true against a closed element — after which nothing can reopen it.
    const onClose = vi.fn();
    render(<Modal open onClose={onClose} title="Settings" />);
    const dialog = screen.getByRole("heading", { name: "Settings" }).closest("dialog");

    fireEvent(dialog!, new Event("cancel", { bubbles: false, cancelable: true }));

    expect(onClose).toHaveBeenCalledOnce();
  });

  it("closes on a backdrop click", () => {
    const onClose = vi.fn();
    render(<Modal open onClose={onClose} title="Settings" />);

    // A click landing on the dialog element itself came from outside the inner panel.
    fireEvent.click(screen.getByRole("heading", { name: "Settings" }).closest("dialog")!);

    expect(onClose).toHaveBeenCalledOnce();
  });

  it("ignores a click inside the panel", () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Settings">
        <p>Body copy</p>
      </Modal>,
    );

    fireEvent.click(screen.getByText("Body copy"));

    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("ConfirmDialog", () => {
  const props = {
    open: true,
    title: "Delete this project permanently?",
    description: "This cannot be undone.",
    confirmLabel: "Yes, delete",
    destructive: true,
  };

  it("focuses cancel, not the destructive action", () => {
    // A modal appearing under the user's hands with the destructive button focused turns
    // a stray Enter into a deletion.
    render(<ConfirmDialog {...props} onConfirm={vi.fn()} onCancel={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  });

  it("confirms when the destructive action is chosen", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(<ConfirmDialog {...props} onConfirm={onConfirm} onCancel={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Yes, delete" }));

    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("cancels without confirming", async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(<ConfirmDialog {...props} onConfirm={onConfirm} onCancel={onCancel} />);

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onCancel).toHaveBeenCalledOnce();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("cannot be dismissed while the action is running", () => {
    // Closing mid-request leaves the user unable to tell whether the deletion happened.
    const onCancel = vi.fn();
    render(<ConfirmDialog {...props} pending onConfirm={vi.fn()} onCancel={onCancel} />);
    const dialog = screen.getByRole("heading", { name: props.title }).closest("dialog");

    fireEvent.click(dialog!);
    fireEvent(dialog!, new Event("cancel", { bubbles: false, cancelable: true }));

    expect(onCancel).not.toHaveBeenCalled();
  });

  it("disables cancel while the action is running", () => {
    render(<ConfirmDialog {...props} pending onConfirm={vi.fn()} onCancel={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  });

  it("disables confirm while the action runs, so it cannot fire twice", async () => {
    // Without this a second click reaches the same handler and the action runs again —
    // two archive requests for one intention.
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(<ConfirmDialog {...props} pending onConfirm={onConfirm} onCancel={vi.fn()} />);
    const confirm = screen.getByRole("button", { name: props.confirmLabel });

    expect(confirm).toBeDisabled();
    expect(confirm).toHaveAttribute("aria-busy", "true");
    await user.click(confirm).catch(() => undefined);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("reports a failure inside the dialog, where the user is looking", () => {
    // The dialog stays open when the action fails, and the page behind it is inert and
    // covered by the backdrop — a message rendered out there cannot be read.
    render(
      <ConfirmDialog
        {...props}
        error="The project could not be deleted."
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    const dialog = screen.getByRole("heading", { name: props.title }).closest("dialog");
    expect(dialog).toContainElement(screen.getByRole("alert"));
    expect(screen.getByRole("alert")).toHaveTextContent("The project could not be deleted.");
  });

  it("shows nothing where the message would go when there is no failure", () => {
    render(<ConfirmDialog {...props} onConfirm={vi.fn()} onCancel={vi.fn()} />);

    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("still offers a retry after a failure", () => {
    // A dialog that reports a failure and then disables its own confirm button leaves the
    // user with nothing to do but cancel and start again.
    render(
      <ConfirmDialog {...props} error="Try again." onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );

    expect(screen.getByRole("button", { name: props.confirmLabel })).toBeEnabled();
  });
});
