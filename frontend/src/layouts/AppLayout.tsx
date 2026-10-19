import {
  Activity,
  Bell,
  FolderKanban,
  LayoutDashboard,
  LineChart,
  Moon,
  ScrollText,
  Server,
  Settings,
  Sun,
  Waypoints,
} from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Button, Select } from "../components/ui";
import { RANGES } from "../lib/utils";
import { useAuth, useProject, useRange, useTheme } from "../state";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/logs", label: "Logs", icon: ScrollText },
  { to: "/traces", label: "Traces", icon: Waypoints },
  { to: "/metrics", label: "Metrics", icon: Activity },
  { to: "/alerts", label: "Alerts", icon: Bell },
  { to: "/analytics", label: "Analytics", icon: LineChart },
  { to: "/services", label: "Services", icon: Server },
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function AppLayout() {
  const { signOut } = useAuth();
  const { projects, projectId, selectProject } = useProject();
  const { range, setRange } = useRange();
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();
  return (
    <div className="grid min-h-screen grid-cols-1 md:grid-cols-[240px_1fr]">
      <aside className="border-b border-zinc-200 bg-zinc-950 text-zinc-100 md:min-h-screen md:border-b-0 md:border-r md:border-zinc-800">
        <div className="flex items-center gap-2 px-5 py-5">
          <span className="h-2.5 w-2.5 rounded-full bg-cyan-400 shadow-[0_0_12px_#22d3ee]" />
          <div>
            <p className="text-sm font-semibold tracking-wide">ObservePro</p>
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-zinc-500">telemetry</p>
          </div>
        </div>
        <nav className="flex gap-1 overflow-auto px-3 pb-4 md:block">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `mb-1 flex items-center gap-2 rounded-md px-3 py-2 text-sm ${isActive ? "bg-cyan-500/15 text-cyan-200" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100"}`
              }
            >
              <item.icon size={16} />
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="min-w-0">
        <header className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 bg-white/80 px-4 py-3 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/80">
          <Select
            aria-label="Project"
            value={projectId ?? ""}
            onChange={(event) => selectProject(event.target.value)}
            className="max-w-xs"
          >
            {projects.length === 0 && <option value="">No project</option>}
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </Select>
          <div className="flex items-center gap-2">
            <div className="flex rounded-md border border-zinc-300 p-0.5 dark:border-zinc-700">
              {RANGES.map((item) => (
                <button
                  key={item.id}
                  className={`rounded px-2 py-1 font-mono text-xs ${range === item.id ? "bg-cyan-600 text-white" : "text-zinc-500"}`}
                  onClick={() => setRange(item.id)}
                  type="button"
                >
                  {item.label}
                </button>
              ))}
            </div>
            <Button variant="secondary" size="icon" aria-label="Toggle theme" onClick={toggle}>
              {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                signOut();
                navigate("/login");
              }}
            >
              Sign out
            </Button>
          </div>
        </header>
        <main className="px-4 py-5 md:px-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
