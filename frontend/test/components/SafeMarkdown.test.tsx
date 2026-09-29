import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SafeMarkdown } from "../../src/components/SafeMarkdown";

describe("SafeMarkdown", () => {
  it("renders plain Markdown normally", () => {
    render(<SafeMarkdown text={"# Heading\n\nSome **bold** text."} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Heading");
    expect(screen.getByText("bold")).toBeInTheDocument();
  });

  it("does not execute raw HTML such as a script tag", () => {
    const { container } = render(
      <SafeMarkdown text={'Before <script>window.__pwned = true;</script> After'} />,
    );
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
    expect(container.querySelector("script")).toBeNull();
  });

  it("neutralizes a javascript: link instead of rendering it as a navigable anchor", () => {
    render(<SafeMarkdown text={"[click me](javascript:alert(1))"} />);
    expect(screen.queryByRole("link", { name: "click me" })).toBeNull();
    expect(screen.getByText("click me")).toBeInTheDocument();
  });

  it("neutralizes a data: link", () => {
    render(<SafeMarkdown text={"[open](data:text/html,<script>alert(1)</script>)"} />);
    expect(screen.queryByRole("link", { name: "open" })).toBeNull();
  });

  it("renders a safe https link with safe attributes", () => {
    render(<SafeMarkdown text={"[docs](https://example.invalid/page)"} />);
    const link = screen.getByRole("link", { name: "docs" });
    expect(link).toHaveAttribute("href", "https://example.invalid/page");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("never creates an <img> element and never auto-loads a remote image", () => {
    const { container } = render(
      <SafeMarkdown text={"![alt text](https://tracker.invalid/pixel.png)"} />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("[alt text]")).toBeInTheDocument();
  });

  it("renders a raw <img onerror=...> tag as inert text, not an executing element", () => {
    const { container } = render(
      <SafeMarkdown text={'<img src=x onerror="window.__pwned2 = true">'} />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect((window as unknown as { __pwned2?: boolean }).__pwned2).toBeUndefined();
  });

  it("gives code blocks a copy control and never a run control", () => {
    render(<SafeMarkdown text={"```\nrm -rf /\n```"} />);
    expect(screen.getByText("rm -rf /")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run/i })).toBeNull();
  });
});
