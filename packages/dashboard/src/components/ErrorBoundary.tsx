import { Component, type ErrorInfo, type ReactNode } from "react";
import { ErrorBox } from "./ui";

/**
 * Keeps a screen that hits unexpected data (for example something an agent wrote in an odd shape) from blanking the
 * whole app: the menu and header stay, the screen shows the error with a retry, and moving to another screen
 * clears it.
 */
export class ScreenErrorBoundary extends Component<{ resetKey: string; children: ReactNode }, { error: Error | null }> {
  override state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error): { error: Error } {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("[asf] a screen crashed", error, info.componentStack);
  }

  override componentDidUpdate(prev: { resetKey: string }): void {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  override render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div className="max-w-3xl" data-testid="screen-error">
        <ErrorBox error={new Error(`This screen hit a problem and could not be shown. ${this.state.error.message}`)} retry={() => this.setState({ error: null })} />
        <p className="mt-3 text-[12.5px] text-ink-3">The rest of AI Software Factory keeps working. If it happens again, the browser console has the details.</p>
      </div>
    );
  }
}
