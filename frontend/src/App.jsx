import { useEffect, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import AICopilotPanel from "./components/AICopilotPanel";
import AppSidebar from "./components/AppSidebar";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "./components/ui/sidebar";
import { Button } from "./components/ui/button";
import { Printer } from "lucide-react";
import PrintReport from "./components/PrintReport";
import { api, errorMessage } from "./api";
import { TooltipProvider } from "./components/ui/tooltip";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "./components/ui/resizable";
import { useDefaultLayout } from "react-resizable-panels";
import {
  Breadcrumb, BreadcrumbItem, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator,
} from "./components/ui/breadcrumb";
import ConfirmDialog from "./components/ConfirmDialog";
import { COMPOSE_EVENT } from "./components/IntakeStart";
import DeviationForm from "./components/DeviationForm";
import DeviationList, { AuditModal } from "./components/DeviationList";
import RiskCard from "./components/RiskCard";
import { RecordHeader, SectionNav } from "./components/RecordHeader";
import { CheckIcon, FileIcon, FlaskIcon, LockIcon, UndoIcon } from "./components/Icons";
import {
  clearNotice, closeAudit, fetchAudit, fetchDeviations, fetchFields, loadDeviation, newDeviation, saveDeviation, undo,
} from "./features/deviationSlice";

/** Light/dark theme: bright by default; a switch to dark is remembered per browser. */
function useTheme() {
  const [theme, setTheme] = useState(() => {
    try {
      // "-v2": older builds saved the OS theme automatically; ignore that so everyone starts bright.
      const saved = localStorage.getItem("aivoa-theme-v2");
      if (saved === "light" || saved === "dark") return saved;
    } catch { /* storage blocked: use the default */ }
    return "light";
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("aivoa-theme-v2", theme); } catch { /* ignore */ }
  }, [theme]);
  return [theme, setTheme];
}

function useMedia(query) {
  const [match, setMatch] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = (e) => setMatch(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [query]);
  return match;
}

/** localStorage that never throws (private windows / blocked storage just skip persistence). */
const safeStorage = {
  getItem: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
  setItem: (k, v) => { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
};

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

export default function App() {
  const dispatch = useDispatch();
  const { mockMode, currentId, dirty, saving, loading, notice, error, form, savedList, past, audit, messages, changeLog } =
    useSelector((s) => s.deviation);
  const [drawer, setDrawer] = useState(false);
  const [confirm, setConfirm] = useState(null);
  // Print preview: null = closed, otherwise the saved change-history rows to include.
  const [printRows, setPrintRows] = useState(null);
  const [printLoading, setPrintLoading] = useState(false);
  const [theme, setTheme] = useTheme();
  // Below 1100px only one pane fits: the view switch toggles Record / Copilot.
  const split = useMedia("(min-width: 1100px)");
  const [view, setView] = useState("record");
  const copilotVisible = split || view === "copilot";
  const [seen, setSeen] = useState(messages.length);
  const paneLayout = useDefaultLayout({ id: "aivoa-panes", panelIds: ["record", "copilot"], storage: safeStorage,
                                        onlySaveAfterUserInteractions: true });
  const recordRef = useRef(null);
  const hasForm = Object.values(form).some((v) => v !== null && v !== "");
  const committed = Boolean(currentId) && !dirty;
  const busy = loading || saving;
  const unread = !copilotVisible && messages.length > seen;

  useEffect(() => {
    dispatch(fetchFields());
    dispatch(fetchDeviations());
  }, [dispatch]);

  useEffect(() => {
    if (copilotVisible) setSeen(messages.length);
  }, [copilotVisible, messages.length]);

  // Success toasts dismiss when their countdown bar finishes (onAnimationEnd), so hovering pauses both.

  // "Saved ✓" moment: after a save completes, show a drawn check for 1.6 s before the settled label.
  const [justSaved, setJustSaved] = useState(false);
  const wasSaving = useRef(false);
  useEffect(() => {
    if (wasSaving.current && !saving && committed) {
      setJustSaved(true);
      const t = setTimeout(() => setJustSaved(false), 1600);
      wasSaving.current = saving;
      return () => clearTimeout(t);
    }
    wasSaving.current = saving;
  }, [saving, committed]);

  // Nudge the commit bar once when the first unsaved change appears.
  const [nudge, setNudge] = useState(0);
  const hadChanges = useRef(false);
  useEffect(() => {
    const has = changeLog.length > 0 && !committed;
    if (has && !hadChanges.current) setNudge((n) => n + 1);
    hadChanges.current = has;
  }, [changeLog.length, committed]);

  // Escape closes the top-most overlay: confirmation, then audit modal, then the drawer.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== "Escape") return;
      if (confirm) setConfirm(null);
      else if (audit.open) dispatch(closeAudit());
      else setDrawer(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [confirm, audit.open, dispatch]);

  /** Run `action`, but ask first if it would throw away uncommitted changes. */
  const guard = (action, what) => {
    if (!dirty) return action();
    const n = changeLog.length || 1;
    setConfirm({
      title: "Discard unsaved changes?",
      body: `${plural(n, "change")} to ${currentId || "this report"} ${n === 1 ? "has" : "have"} not been saved. ${what} will discard ${n === 1 ? "it" : "them"}.`,
      confirmLabel: "Discard changes",
      onConfirm: () => { setConfirm(null); action(); },
    });
  };

  // With nothing loaded, "New deviation" means "start an intake": open the Copilot message box.
  const startNew = () => {
    if (!hasForm) {
      setView("copilot");
      window.dispatchEvent(new Event(COMPOSE_EVENT));
      return;
    }
    guard(() => dispatch(newDeviation()), "Starting a new report");
  };
  const openRecord = (id) => {
    if (id === currentId && !dirty) return setDrawer(false);
    guard(() => { dispatch(loadDeviation(id)); setDrawer(false); setView("record"); }, `Opening ${id}`);
  };

  /** Open the print preview; a saved record brings its full change history from the server. */
  const openPrint = async () => {
    setPrintLoading(true);
    try {
      const rows = currentId ? await api.audit(currentId) : [];
      setPrintRows({ rows });
    } catch (e) {
      setPrintRows({ rows: [], error: errorMessage(e) }); // still print the record; say why history is missing
    } finally {
      setPrintLoading(false);
    }
  };

  const commitLabel = saving ? "Saving…" : committed ? `Saved as ${currentId}` : currentId ? "Save changes" : "Save report";

  const recordPane = (
    <main ref={recordRef} className={`record ${loading && !hasForm ? "is-loading" : ""}`}>
      <RecordHeader />
      <div className="record-body">
        <SectionNav scrollRoot={recordRef} />
        <div className="record-content">
          <p className="readonly-note">
            <LockIcon size={13} /> You can't type in these fields. Ask the AI assistant to change anything; every change is kept in the change history.
          </p>
          <DeviationForm />
          <RiskCard />
        </div>
      </div>
      <footer key={nudge} className={`commit-bar ${nudge ? "nudge" : ""}`}>
        <p className="commit-meta" aria-live="polite">
          {committed ? (
            <><CheckIcon size={14} className="ok" /> Everything is saved.</>
          ) : hasForm && changeLog.length > 0 ? (
            <>{plural(changeLog.length, "unsaved change")}. Saving adds {changeLog.length === 1 ? "it" : "them"} to the change history.</>
          ) : hasForm ? (
            <>Ready to save.</>
          ) : (
            <>Nothing to save yet.</>
          )}
        </p>
        <button className={`btn btn-primary commit-btn ${saving ? "is-saving" : ""} ${justSaved ? "just-saved" : ""}`}
                onClick={() => dispatch(saveDeviation())} disabled={!hasForm || busy || committed} aria-busy={saving}>
          {saving ? <span className="btn-spinner" aria-hidden="true" />
            : justSaved ? <svg className="draw-check" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12.5 9.5 18 20 6" /></svg>
            : <CheckIcon size={16} strokeWidth={2.5} />}
          {justSaved ? "Saved" : commitLabel}
        </button>
      </footer>
    </main>
  );

  return (
    <TooltipProvider delayDuration={200}>
    <SidebarProvider className={`shell view-${view}`}>
      <AppSidebar
        currentId={currentId}
        savedCount={savedList.length}
        newDisabled={busy}
        theme={theme}
        onNew={startNew}
        onRecent={() => setDrawer(true)}
        onAudit={() => currentId && dispatch(fetchAudit(currentId))}
        onToggleTheme={() => setTheme(theme === "dark" ? "light" : "dark")}
      />
      <SidebarInset className="shell-inset">
        {/* ---------- inset header (dashboard-01 style) ---------- */}
        <header className="inset-header">
          <SidebarTrigger className="-ml-1" />
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem className="hidden md:block">Deviations</BreadcrumbItem>
              <BreadcrumbSeparator className="hidden md:block" />
              <BreadcrumbItem>
                <BreadcrumbPage>{currentId || "New report"}</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
          <div className="inset-actions">
            {mockMode && (
              <span className="env-badge mock" title="No GROQ_API_KEY configured: the offline rule-based parser is answering">Mock mode</span>
            )}
            <div className="view-switch" role="tablist" aria-label="View">
              <button role="tab" aria-selected={view === "record"} className={view === "record" ? "on" : ""} onClick={() => setView("record")}>
                <FileIcon size={14} /> Report
              </button>
              <button role="tab" aria-selected={view === "copilot"} className={view === "copilot" ? "on" : ""} onClick={() => setView("copilot")}>
                <FlaskIcon size={14} /> Assistant
                {(unread || (loading && !copilotVisible)) && <i className={`vs-dot ${loading ? "busy" : ""}`} aria-label="New activity" />}
              </button>
            </div>
            <Button variant="ghost" size="sm" onClick={() => dispatch(undo())} disabled={!past.length || busy}
                    title="Revert the last change (you can also type “undo”)">
              <UndoIcon size={15} /><span className="btn-text">Undo</span>
            </Button>
            <Button variant="outline" size="sm" onClick={openPrint} disabled={!hasForm || busy || printLoading}
                    title="Preview, print or save the full report as PDF">
              <Printer size={15} /><span className="btn-text">{printLoading ? "Preparing…" : "Print report"}</span>
            </Button>
          </div>
        </header>

        {split ? (
          /* Desktop: record and Copilot side by side; drag the divider to resize (layout is remembered). */
          <ResizablePanelGroup orientation="horizontal" className="panes"
                               defaultLayout={paneLayout.defaultLayout} onLayoutChanged={paneLayout.onLayoutChanged}>
            <ResizablePanel id="record" defaultSize="62" minSize="40" className="pane-slot">
              {recordPane}
            </ResizablePanel>
            <ResizableHandle className="pane-handle" aria-label="Resize record and Copilot" />
            <ResizablePanel id="copilot" defaultSize="38" minSize="26" maxSize="55" className="pane-slot">
              <AICopilotPanel />
            </ResizablePanel>
          </ResizablePanelGroup>
        ) : (
          /* Narrow screens: one pane at a time, chosen with the Record / Copilot switch. */
          <div className="panes">
            {recordPane}
            <AICopilotPanel />
          </div>
        )}
      </SidebarInset>

      {drawer && (
        <>
          <div className="drawer-backdrop" onClick={() => setDrawer(false)} />
          <DeviationList onClose={() => setDrawer(false)} onOpen={openRecord} busy={busy} />
        </>
      )}
      {(notice || error) && (
        <div key={error || notice} className={`toast ${error ? "toast-error" : ""}`} onClick={() => dispatch(clearNotice())}
             role={error ? "alert" : "status"}>
          {error || notice}
          {!error && <span className="toast-timer" aria-hidden="true" onAnimationEnd={() => dispatch(clearNotice())} />}
        </div>
      )}
      <AuditModal />
      {confirm && <ConfirmDialog {...confirm} onCancel={() => setConfirm(null)} />}
      {printRows && <PrintReport auditRows={printRows.rows} historyError={printRows.error} onClose={() => setPrintRows(null)} />}
    </SidebarProvider>
    </TooltipProvider>
  );
}
