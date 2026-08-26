import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Alert, Button, EmptyState, Field, StatusBadge } from "@/components/ui";
import { ProjectCard } from "@/features/projects/ProjectCard";
import { Pagination } from "@/features/projects/Pagination";
import { ProjectList } from "@/features/projects/ProjectList";
import { ProjectListSkeleton } from "@/features/projects/ProjectListSkeleton";
import type { PageMeta, ProjectResponse } from "@factory/contracts";

const project: ProjectResponse = {
  id: "11111111-1111-4111-8111-111111111111",
  name: "Restaurant System",
  slug: "restaurant-system",
  description: "POS and inventory.",
  status: "draft",
  created_at: "2026-01-15T12:00:00Z",
  updated_at: "2026-01-15T12:00:00Z",
  archived_at: null,
};

const meta: PageMeta = {
  page: 1,
  page_size: 20,
  total: 1,
  total_pages: 1,
  has_next: false,
  has_previous: false,
};

describe("Button", () => {
  it("renders its label", () => {
    render(<Button>Save</Button>);

    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });

  it("blocks a second click while loading", async () => {
    // A double-submit on a create form makes two projects.
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Save
      </Button>,
    );
    const button = screen.getByRole("button");

    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    await userEvent.click(button).catch(() => undefined);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("calls its handler when idle", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Save</Button>);

    await userEvent.click(screen.getByRole("button"));

    expect(onClick).toHaveBeenCalledOnce();
  });
});

describe("Field", () => {
  it("associates the label with the input", async () => {
    render(<Field label="Email" name="email" />);

    // getByLabelText only finds it if the association is real.
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");

    expect(screen.getByLabelText("Email")).toHaveValue("ada@example.com");
  });

  it("announces an error and marks the input invalid", () => {
    render(<Field label="Email" name="email" error="Enter a valid email address" />);

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Enter a valid email address");
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-describedby", "email-error");
  });

  it("hides the hint once there is an error", () => {
    render(<Field label="Email" name="email" hint="We never share this" error="Required" />);

    expect(screen.queryByText("We never share this")).not.toBeInTheDocument();
  });
});

describe("Alert", () => {
  it("uses role=alert for errors so it is announced immediately", () => {
    render(<Alert variant="error">Something failed</Alert>);

    expect(screen.getByRole("alert")).toHaveTextContent("Something failed");
  });

  it("uses role=status for non-urgent messages", () => {
    render(<Alert variant="success">Saved</Alert>);

    expect(screen.getByRole("status")).toHaveTextContent("Saved");
  });
});

describe("StatusBadge", () => {
  it.each([
    ["draft", "Draft"],
    ["archived", "Archived"],
  ])("spells out %s as text, not colour alone", (status, label) => {
    render(<StatusBadge status={status} />);

    expect(screen.getByTestId("project-status")).toHaveTextContent(label);
  });
});

describe("ProjectCard", () => {
  it("links to the project and shows its status", () => {
    render(<ProjectCard project={project} />);

    expect(screen.getByRole("link", { name: "Restaurant System" })).toHaveAttribute(
      "href",
      `/projects/${project.id}`,
    );
    expect(screen.getByTestId("project-status")).toHaveTextContent("Draft");
  });

  it("tolerates an unparseable date rather than crashing the list", () => {
    render(<ProjectCard project={{ ...project, created_at: "not-a-date" }} />);

    expect(screen.getByText(/unknown/)).toBeInTheDocument();
  });

  it("omits the description when there is none", () => {
    render(<ProjectCard project={{ ...project, description: "" }} />);

    expect(screen.queryByText("POS and inventory.")).not.toBeInTheDocument();
  });
});

describe("ProjectList", () => {
  it("renders projects when there are some", () => {
    render(<ProjectList projects={[project]} meta={meta} />);

    expect(screen.getAllByTestId("project-card")).toHaveLength(1);
  });

  it("explains what to do next when empty", () => {
    // An empty collection is a normal state and the moment a new user is most lost.
    render(<ProjectList projects={[]} meta={{ ...meta, total: 0 }} />);

    expect(screen.getByText("No projects yet")).toBeInTheDocument();
    expect(screen.getByText(/Create your first project/)).toBeInTheDocument();
  });
});

describe("Pagination", () => {
  it("is hidden when there is only one page", () => {
    const { container } = render(<Pagination meta={meta} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("links to neighbouring pages", () => {
    render(
      <Pagination
        meta={{ ...meta, page: 2, total: 60, total_pages: 3, has_next: true, has_previous: true }}
      />,
    );

    expect(screen.getByRole("link", { name: /Previous/ })).toHaveAttribute(
      "href",
      "/projects?page=1",
    );
    expect(screen.getByRole("link", { name: /Next/ })).toHaveAttribute(
      "href",
      "/projects?page=3",
    );
  });

  it("disables navigation at the first page", () => {
    render(<Pagination meta={{ ...meta, total_pages: 2, has_next: true }} />);

    expect(screen.queryByRole("link", { name: /Previous/ })).not.toBeInTheDocument();
  });
});

describe("EmptyState", () => {
  it("renders an optional action", () => {
    render(<EmptyState title="Nothing" description="Add one" action={<button>Add</button>} />);

    expect(screen.getByRole("button", { name: "Add" })).toBeInTheDocument();
  });
});

describe("ProjectListSkeleton", () => {
  it("places one card-shaped placeholder per row it expects", () => {
    render(<ProjectListSkeleton rows={4} />);

    expect(screen.getByTestId("project-skeleton").querySelectorAll("li")).toHaveLength(4);
  });

  it("announces that it is loading, once", () => {
    // A screen reader user needs to be told "loading" — not to have four decorative bars
    // described to them, which is what an unhidden placeholder produces.
    render(<ProjectListSkeleton />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading projects");
    expect(screen.getByTestId("project-skeleton").querySelector("ul")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
  });
});
