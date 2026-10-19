import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, getProjectId, getToken, setProjectId, setToken } from "./api/client";
import type { Project } from "./types";
import { type RangeId } from "./lib/utils";

interface AuthState {
  token: string | null;
  signIn: (token: string) => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(getToken());
  const value = useMemo<AuthState>(
    () => ({
      token,
      signIn: (next) => {
        setToken(next);
        setTokenState(next);
      },
      signOut: () => {
        setToken(null);
        setTokenState(null);
      },
    }),
    [token],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider is missing");
  return value;
}

const RangeContext = createContext<{ range: RangeId; setRange: (range: RangeId) => void } | null>(null);

export function RangeProvider({ children }: { children: ReactNode }) {
  const [range, setRange] = useState<RangeId>("1h");
  return <RangeContext.Provider value={{ range, setRange }}>{children}</RangeContext.Provider>;
}

export function useRange() {
  const value = useContext(RangeContext);
  if (!value) throw new Error("RangeProvider is missing");
  return value;
}

const ProjectContext = createContext<{
  projectId: string | null;
  projects: Project[];
  selectProject: (id: string) => void;
  loading: boolean;
} | null>(null);

export function ProjectProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const [projectId, setId] = useState<string | null>(getProjectId());
  const query = useQuery({
    queryKey: ["projects", token],
    enabled: Boolean(token),
    queryFn: () => api<Project[]>("/api/v1/projects"),
  });
  useEffect(() => {
    const projects = query.data ?? [];
    if (!projects.length) return;
    if (!projectId || !projects.some((project) => project.id === projectId)) {
      setId(projects[0].id);
      setProjectId(projects[0].id);
    }
  }, [query.data, projectId]);
  const value = useMemo(
    () => ({
      projectId,
      projects: query.data ?? [],
      loading: query.isLoading,
      selectProject: (id: string) => {
        setProjectId(id);
        setId(id);
      },
    }),
    [projectId, query.data, query.isLoading],
  );
  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProject() {
  const value = useContext(ProjectContext);
  if (!value) throw new Error("ProjectProvider is missing");
  return value;
}

export function useTheme() {
  const [theme, setTheme] = useState<"dark" | "light">(() => (document.documentElement.classList.contains("dark") ? "dark" : "light"));
  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.classList.toggle("dark", next === "dark");
    localStorage.setItem("observe.theme", next);
    setTheme(next);
  }
  useEffect(() => {
    const stored = localStorage.getItem("observe.theme");
    if (stored === "light" || stored === "dark") {
      document.documentElement.classList.toggle("dark", stored === "dark");
      setTheme(stored);
    }
  }, []);
  return { theme, toggle };
}
