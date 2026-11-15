import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StartScreen } from "../../src/components/StartScreen";

describe("StartScreen", () => {
  it("starts a call", () => {
    const onStart = vi.fn();
    render(<StartScreen onStart={onStart} starting={false} notice={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Talk to Tom" }));
    expect(onStart).toHaveBeenCalledOnce();
  });

  it("disables the button while starting", () => {
    render(<StartScreen onStart={vi.fn()} starting notice={null} />);
    expect(screen.getByRole("button", { name: "Calling Tom…" })).toBeDisabled();
  });

  it("shows the notice and how to review the last call", () => {
    render(
      <StartScreen
        onStart={vi.fn()}
        starting={false}
        notice="The call has ended. Thanks for visiting!"
        lastConversationId="c123"
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("The call has ended");
    expect(screen.getByText("uv run review-call c123")).toBeInTheDocument();
  });

  it("hides the review hint before any call", () => {
    render(<StartScreen onStart={vi.fn()} starting={false} notice={null} />);
    expect(screen.queryByText(/review-call/)).not.toBeInTheDocument();
  });
});
