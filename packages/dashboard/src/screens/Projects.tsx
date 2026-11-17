import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { FolderPicker } from "../components/FolderPicker";
import { Badge, Empty, ErrorBox, Icon, Skeleton, toastError } from "../components/ui";
import { api } from "../lib/api";
import { useFsHome, useProjects } from "../lib/queries";
import { href, navigate } from "../lib/router";
import { PHASE_LABELS } from "../lib/types";
import { Logo } from "../components/Logo";

export function ProjectsScreen({ openPath = null }: { openPath?: string | null }) {
  const q = useProjects();
  const fsHome = useFsHome();
  const [picker, setPicker] = useState<{ path: string | null } | null>(null);
  // Deep link #/open?path=... (asf up in a folder that is not a project yet) opens the picker there.
  const pickerOpen = picker !== null || openPath !== null;
  const pickerPath = picker?.path ?? openPath ?? null;
  const closePicker = () => {
    setPicker(null);
    if (openPath !== null) navigate("#/", true);
  };
  const launch = fsHome.data?.launchDir && !fsHome.data.launchIsProject ? fsHome.data.launchDir : null;
  const qc = useQueryClient();
  const [root, setRoot] = useState("");
  const [init, setInit] = useState(false);
  const open = useMutation({
    mutationFn: (b: { root: string; init: boolean }) =>
      api<{ id: string; name: string; root: string }>("POST", "/api/projects", b),
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: ["projects"] });
      navigate(href(r.id, ""));
    },
  });

  return (
    <div className="canvas min-h-full">
      <div className="mx-auto max-w-5xl px-6 py-10">
        <section
          className="fade-up relative mb-10 overflow-hidden rounded-[20px] border border-white/10 px-9 py-10 text-white shadow-(--shadow-lg) max-[700px]:px-5"
          style={{
            background:
              "radial-gradient(560px 280px at 0% 0%, rgb(20 184 166 / 0.38), transparent 70%), radial-gradient(520px 320px at 100% 110%, rgb(8 145 178 / 0.42), transparent 70%), linear-gradient(160deg, #0a1415 0%, #060a0b 100%)",
          }}
        >
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0"
            style={{
              backgroundImage: "radial-gradient(rgb(255 255 255 / 0.13) 1px, transparent 1.3px)",
              backgroundSize: "20px 20px",
              maskImage: "radial-gradient(640px 320px at 30% 30%, #000 10%, transparent 80%)",
            }}
          />
          <svg
            aria-hidden
            viewBox="0 0 100 100"
            className="pointer-events-none absolute -top-10 -right-12 h-90 w-90 opacity-[0.07] max-[700px]:hidden"
            fill="none"
            stroke="#fff"
            strokeWidth="1.2"
            strokeLinejoin="round"
          >
            <path d="M50 10 84.6 30v40L50 90 15.4 70V30Z" />
            <path d="M15.4 30 50 50l34.6-20M50 50v40" />
            <path d="M32.7 20 67.3 40v40M67.3 20 32.7 40v40" strokeDasharray="2 3" />
          </svg>
          <div className="relative flex flex-wrap items-center justify-between gap-6">
            <div className="max-w-xl">
              <div className="mb-5 flex items-center gap-2.5">
                <Logo size={36} />
                <span className="text-[15px] font-bold tracking-[-0.02em]">
                  <span className="bg-[linear-gradient(90deg,#5eead4,#67e8f9)] bg-clip-text text-transparent">
                    AI
                  </span>{" "}
                  Software Factory
                </span>
              </div>
              <p className="text-[34px] leading-[1.1] font-extrabold tracking-[-0.035em] max-[700px]:text-[26px]">
                Your whole AI software team,{" "}
                <span className="bg-[linear-gradient(90deg,#5eead4,#67e8f9)] bg-clip-text text-transparent">
                  on your own machine.
                </span>
              </p>
              <p className="mt-3.5 max-w-[52ch] text-[14.5px] leading-relaxed text-white/65">
                Describe an app. Approve each step. Watch a PM, designer, engineers, QA, and a reviewer build
                it in parallel, live.
              </p>
            </div>
            <div className="flex flex-col items-start gap-2">
              <button
                className="btn h-11 rounded-[10px] border-transparent bg-[linear-gradient(135deg,#5eead4,#22d3ee)] px-5 text-[14px] font-semibold text-[#032523] shadow-[0_10px_30px_-10px_rgb(45_212_191_/_0.7)] hover:brightness-110"
                onClick={() => setPicker({ path: null })}
                data-testid="open-folder"
              >
                <Icon name="folder" size={16} /> Open a folder
              </button>
              <span className="text-[12px] text-white/55">A new folder, or an existing project</span>
            </div>
          </div>
          <div className="relative mt-8 flex flex-wrap gap-2">
            {["PM", "Tech lead", "Designer", "Backend", "Frontend", "QA", "Reviewer", "DevOps"].map((r) => (
              <span
                key={r}
                className="mono inline-flex items-center gap-1.5 rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-[11.5px] font-medium text-white/75 backdrop-blur-sm"
              >
                <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-[#5eead4]" />
                {r}
              </span>
            ))}
          </div>
        </section>
        {launch && openPath === null && (
          <div
            className="mb-8 flex flex-wrap items-center gap-4 rounded-xl border border-l-4 border-rule shadow-(--shadow-sm) border-l-accent bg-surface px-5 py-4"
            data-testid="launch-banner"
          >
            <div className="min-w-0 flex-1">
              <div className="text-[14px] font-semibold">
                Open <span className="mono break-all">{launch}</span> in AI Software Factory?
              </div>
              <div className="text-[12.5px] text-ink-3">
                You ran <code className="mono">asf up</code> in this folder. It is not an AI Software Factory
                project yet.
              </div>
            </div>
            <button className="btn btn-primary" onClick={() => setPicker({ path: launch })}>
              Open a folder
            </button>
          </div>
        )}
        <FolderPicker
          key={pickerPath ?? "_"}
          open={pickerOpen}
          onClose={closePicker}
          initialPath={pickerPath}
        />

        <div className="grid grid-cols-[minmax(0,1fr)_320px] gap-8 max-[900px]:grid-cols-1">
          <section aria-labelledby="known">
            <div className="mb-4 flex items-end justify-between gap-3">
              <div>
                <div className="mono mb-1 flex items-center gap-2 text-[10.5px] font-medium tracking-[0.14em] text-accent uppercase">
                  <span aria-hidden className="h-px w-5 bg-accent" />
                  Known projects
                </div>
                <h1 id="known" className="text-[26px] leading-tight font-bold tracking-[-0.03em]">
                  Projects
                </h1>
              </div>
              {q.data?.length ? (
                <span className="mono text-[12px] text-ink-3">
                  {q.data.length} project{q.data.length === 1 ? "" : "s"}
                </span>
              ) : null}
            </div>
            {q.error ? (
              <ErrorBox error={q.error} retry={() => void q.refetch()} />
            ) : q.isLoading ? (
              <Skeleton rows={4} />
            ) : !q.data?.length ? (
              <Empty title="No projects yet">
                Open a folder on the right. AI Software Factory keeps its state in a{" "}
                <code className="mono">.asf</code> folder inside it.
              </Empty>
            ) : (
              <ul className="flex flex-col gap-2.5">
                {q.data.map((p) => (
                  <li key={p.id}>
                    <button
                      className="group card flex w-full items-center gap-4 rounded-xl px-4 py-3.5 text-left transition-[box-shadow,transform,border-color] duration-150 hover:-translate-y-px hover:border-[color-mix(in_srgb,var(--accent)_45%,var(--rule))] hover:shadow-(--shadow-md) disabled:opacity-60"
                      disabled={open.isPending}
                      onClick={() =>
                        p.open
                          ? navigate(href(p.id, ""))
                          : open.mutate({ root: p.root, init: false }, { onError: toastError })
                      }
                    >
                      <span
                        aria-hidden
                        className="bg-brand flex h-10 w-10 shrink-0 items-center justify-center rounded-[11px] text-[15px] font-bold text-brand-ink uppercase shadow-(--shadow-sm) ring-1 ring-black/5"
                      >
                        {(p.name ?? p.root.split(/[\\/]/).pop() ?? "?").slice(0, 1)}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="text-[15px] font-semibold">
                          {p.name ?? p.root.split(/[\\/]/).pop()}
                        </div>
                        <div className="mono truncate text-[12px] text-ink-3">{p.root}</div>
                      </div>
                      {p.phase && <Badge>{PHASE_LABELS[p.phase] ?? p.phase}</Badge>}
                      {!p.exists ? (
                        <Badge tone="danger">missing</Badge>
                      ) : p.open ? (
                        <Badge tone="ok">open</Badge>
                      ) : (
                        <Badge>closed</Badge>
                      )}
                      <Icon
                        name="arrow"
                        className="text-ink-3 transition-transform group-hover:translate-x-0.5 group-hover:text-accent"
                      />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section
            aria-labelledby="openp"
            className="relative self-start overflow-hidden card rounded-xl p-5 before:absolute before:inset-x-0 before:top-0 before:h-0.5 before:bg-(image:--brand-grad) before:content-['']"
          >
            <h2 id="openp" className="mb-1 text-[15px] font-bold tracking-[-0.02em]">
              Open a project
            </h2>
            <p className="mb-4 text-[13px] text-ink-2">
              Any folder on this machine. New folders can be initialized here.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (root.trim()) open.mutate({ root: root.trim(), init });
              }}
            >
              <label className="label" htmlFor="root">
                Folder path
              </label>
              <input
                id="root"
                className="field mono"
                placeholder="C:\code\my-app"
                value={root}
                onChange={(e) => setRoot(e.target.value)}
              />
              <label className="mt-3 flex items-center gap-2 text-[13px]">
                <input type="checkbox" checked={init} onChange={(e) => setInit(e.target.checked)} />
                Initialize if needed (<code className="mono text-[12px]">asf init</code>)
              </label>
              {open.error && (
                <div className="mt-3">
                  <ErrorBox error={open.error} />
                </div>
              )}
              <button
                type="submit"
                className="btn btn-primary mt-4"
                disabled={!root.trim() || open.isPending}
              >
                {open.isPending ? "Opening…" : "Open project"}
              </button>
            </form>
          </section>
        </div>
      </div>
    </div>
  );
}
