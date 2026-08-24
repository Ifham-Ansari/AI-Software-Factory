import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CodeInput, PasswordField } from "@/components/ui";

describe("PasswordField", () => {
  it("starts masked and reveals on toggle", async () => {
    render(<PasswordField label="Password" name="password" />);
    const input = screen.getByLabelText("Password");
    const toggle = screen.getByRole("button", { name: "Show password" });

    expect(input).toHaveAttribute("type", "password");
    expect(toggle).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(toggle);

    expect(input).toHaveAttribute("type", "text");
    expect(screen.getByRole("button", { name: "Hide password" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("does not change what was typed when toggled", async () => {
    render(<PasswordField label="Password" name="password" />);
    const input = screen.getByLabelText("Password");

    await userEvent.type(input, "a-secret-passphrase");
    await userEvent.click(screen.getByRole("button", { name: "Show password" }));

    expect(input).toHaveValue("a-secret-passphrase");
  });

  it("hides the hint once there is an error", () => {
    render(
      <PasswordField
        label="Password"
        name="password"
        hint="At least 8 characters."
        error="Too short"
      />,
    );

    expect(screen.queryByText("At least 8 characters.")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Too short");
  });
});

describe("CodeInput", () => {
  it("renders one labelled box per digit", () => {
    render(<CodeInput name="code" />);

    for (let index = 1; index <= 6; index += 1) {
      expect(screen.getByLabelText(`Digit ${index} of 6`)).toBeInTheDocument();
    }
  });

  it("advances focus as each digit is typed", async () => {
    render(<CodeInput name="code" />);

    await userEvent.type(screen.getByLabelText("Digit 1 of 6"), "1");
    expect(screen.getByLabelText("Digit 2 of 6")).toHaveFocus();

    await userEvent.type(screen.getByLabelText("Digit 2 of 6"), "2");
    expect(screen.getByLabelText("Digit 3 of 6")).toHaveFocus();
  });

  it("moves back on backspace from an empty box", async () => {
    render(<CodeInput name="code" />);

    await userEvent.type(screen.getByLabelText("Digit 1 of 6"), "1");
    const second = screen.getByLabelText("Digit 2 of 6");
    second.focus();

    await userEvent.keyboard("{Backspace}");

    expect(screen.getByLabelText("Digit 1 of 6")).toHaveFocus();
  });

  it("distributes a pasted code across every box", async () => {
    render(<CodeInput name="code" />);

    await userEvent.click(screen.getByLabelText("Digit 1 of 6"));
    await userEvent.paste("123456");

    for (let index = 1; index <= 6; index += 1) {
      expect(screen.getByLabelText(`Digit ${index} of 6`)).toHaveValue(String(index));
    }
  });

  it("shows a validation error", () => {
    render(<CodeInput name="code" error="Enter all 6 digits." />);

    expect(screen.getByRole("alert")).toHaveTextContent("Enter all 6 digits.");
  });
});
