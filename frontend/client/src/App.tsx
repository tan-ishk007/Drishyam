/**
 * DRISHYAM local integration: public pages retain their supplied visuals;
 * `/workspace` restores the durable authenticated session before evaluating access.
 */
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/NotFound";
import { Redirect, Route, Switch } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary";
import { SessionProvider, useSession } from "./contexts/SessionContext";
import { ThemeProvider } from "./contexts/ThemeContext";
import Home from "./pages/Home";
import Login from "./pages/Login";
import Workspace from "./pages/Workspace";

function ProtectedWorkspace() {
  const { user, isRestoring } = useSession();
  if (isRestoring) return <main className="grid min-h-screen place-items-center bg-[#1f1b17] px-6 text-center text-[#f5e8d4]"><p className="font-mono text-xs font-bold tracking-[.16em]">RESTORING SECURE SESSION…</p></main>;
  return user ? <Workspace /> : <Redirect to="/login" />;
}

function Router() {
  return (
    <Switch>
      <Route path="/" component={Home} />
      <Route path="/login" component={Login} />
      <Route path="/workspace" component={ProtectedWorkspace} />
      <Route path="/404" component={NotFound} />
      <Route component={NotFound} />
    </Switch>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <SessionProvider>
        <ThemeProvider defaultTheme="light">
          <TooltipProvider>
            <Toaster />
            <Router />
          </TooltipProvider>
        </ThemeProvider>
      </SessionProvider>
    </ErrorBoundary>
  );
}
