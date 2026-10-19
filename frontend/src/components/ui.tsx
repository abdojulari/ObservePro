import { Slot } from "@radix-ui/react-slot";
import * as Dialog from "@radix-ui/react-dialog";
import * as Dropdown from "@radix-ui/react-dropdown-menu";
import { cva, type VariantProps } from "class-variance-authority";
import { type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { cn, severityClass } from "../lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-cyan-600 text-white hover:bg-cyan-500",
        secondary: "border border-zinc-300 bg-white hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800",
        ghost: "hover:bg-zinc-100 dark:hover:bg-zinc-800",
        danger: "bg-red-700 text-white hover:bg-red-600",
      },
      size: {
        default: "h-9 px-3",
        sm: "h-8 px-2 text-xs",
        icon: "h-8 w-8",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <section className={cn("rounded-xl border border-zinc-200 bg-white/90 shadow-sm dark:border-zinc-800 dark:bg-zinc-950/80", className)}>
      {children}
    </section>
  );
}

export function CardHeader({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
      <h2 className="text-sm font-semibold tracking-wide">{title}</h2>
      {action}
    </div>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn(
        "h-9 w-full rounded-md border border-zinc-300 bg-white px-3 text-sm outline-none ring-cyan-500 focus:ring-2 dark:border-zinc-700 dark:bg-zinc-950",
        props.className,
      )}
    />
  );
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={cn(
        "w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none ring-cyan-500 focus:ring-2 dark:border-zinc-700 dark:bg-zinc-950",
        props.className,
      )}
    />
  );
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={cn(
        "h-9 rounded-md border border-zinc-300 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-950",
        props.className,
      )}
    />
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span className={cn("inline-flex rounded px-1.5 py-0.5 font-mono text-[11px] font-medium tracking-wide", severityClass(severity))}>
      {severity}
    </span>
  );
}

export function StatusDot({ health }: { health: string }) {
  const color =
    health === "healthy" ? "bg-emerald-500" : health === "degraded" ? "bg-amber-500" : health === "inactive" ? "bg-zinc-500" : "bg-sky-500";
  return (
    <span className="inline-flex items-center gap-2 text-xs uppercase tracking-wide text-zinc-500">
      <span className={cn("h-2 w-2 rounded-full", color)} />
      {health}
    </span>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="px-6 py-16 text-center">
      <p className="text-base font-medium">{title}</p>
      <p className="mx-auto mt-2 max-w-md text-sm text-zinc-500">{body}</p>
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">{message}</div>;
}

export function Modal({
  open,
  onOpenChange,
  title,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/60" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(520px,calc(100%-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-zinc-700 bg-zinc-950 p-5 text-zinc-100 shadow-2xl">
          <Dialog.Title className="text-lg font-semibold">{title}</Dialog.Title>
          <div className="mt-4">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function Menu({ trigger, children }: { trigger: ReactNode; children: ReactNode }) {
  return (
    <Dropdown.Root>
      <Dropdown.Trigger asChild>{trigger}</Dropdown.Trigger>
      <Dropdown.Portal>
        <Dropdown.Content className="z-30 min-w-44 rounded-md border border-zinc-700 bg-zinc-950 p-1 text-sm text-zinc-100 shadow-xl" sideOffset={6}>
          {children}
        </Dropdown.Content>
      </Dropdown.Portal>
    </Dropdown.Root>
  );
}

export function MenuItem({ children, onSelect }: { children: ReactNode; onSelect?: () => void }) {
  return (
    <Dropdown.Item className="cursor-pointer rounded px-2 py-1.5 outline-none hover:bg-zinc-800" onSelect={onSelect}>
      {children}
    </Dropdown.Item>
  );
}

export function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="overflow-auto rounded-md bg-zinc-100 p-3 font-mono text-xs leading-relaxed text-zinc-800 dark:bg-black/40 dark:text-zinc-200">
      {JSON.stringify(value ?? {}, null, 2)}
    </pre>
  );
}
