import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { App } from "../src/App";

describe("App", () => {
  it("renders the app shell", () => {
    render(<App />);
    expect(screen.getByText("S-CORE Docs Assistant")).toBeInTheDocument();
  });
});
