/**
 * deviationSlice - the single client-side store for the Log Deviation screen.
 *
 * Why Redux: the form, the chat and the risk card must all reflect the SAME
 * state returned by the AI agent. The backend is the only thing that changes
 * the form; this slice just stores its responses (the UI never edits fields).
 */
import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { api, errorMessage } from "../api";

const WELCOME = {
  at: Date.now(),
  role: "assistant",
  content:
    "Hi! Give me a quality problem report: paste the email or text, or upload a PDF or photo. " +
    "I will fill in the form for you and check how risky it is.",
  meta: { icon: "info" },
};

/** Human-readable file type for the chat file card. */
export function fileKind(name = "") {
  const ext = name.split(".").pop().toLowerCase();
  return { pdf: "PDF Document", jpg: "JPEG Image", jpeg: "JPEG Image", png: "PNG Image",
           eml: "Email Message", txt: "Text File" }[ext] || "Document";
}

const initialState = {
  registry: null, // { sections, risk_section, fields, tiers }
  copilotStatus: "idle", // idle | working | done  (status dot in the Copilot header)
  audit: { id: null, rows: [], open: false },
  mockMode: false,
  model: null, // LLM shown in the brand bar (null in mock mode)
  form: {},
  userOverrides: {},
  changeLog: [], // all AI/user changes since the last save -> sent to the audit trail
  highlight: { fields: [], token: 0 }, // fields that just changed (token restarts the CSS flash)
  messages: [WELCOME],
  loading: false,
  saving: false,
  error: null,
  currentId: null, // deviation_id once saved / loaded
  dirty: false,
  savedList: [],
  notice: null,
  past: [], // undo stack: snapshots of {form, userOverrides, changeLog, dirty} before each AI change
};

const UNDO_LIMIT = 20;

function snapshot(s) {
  // currentId is part of the snapshot: undoing a "log" must re-attach the restored values to their record,
  // otherwise the next commit would create a duplicate instead of updating it.
  return { form: s.form, userOverrides: s.userOverrides, changeLog: s.changeLog, dirty: s.dirty, currentId: s.currentId };
}

/** Restore the previous snapshot. Undone changes are dropped from the change log, so they never reach the audit. */
function undoLast(s, labels) {
  const prev = s.past.pop();
  if (!prev) {
    s.messages.push({ at: Date.now(), role: "assistant", content: "Nothing to undo yet.", meta: { icon: "info" } });
    return;
  }
  const keys = [...new Set([...Object.keys(prev.form), ...Object.keys(s.form)])];
  const reverted = keys.filter((k) => (prev.form[k] ?? null) !== (s.form[k] ?? null));
  Object.assign(s, prev);
  s.highlight = { fields: reverted, token: s.highlight.token + 1 };
  const names = reverted.slice(0, 4).map((k) => labels[k] || k).join(", ");
  s.messages.push({
    at: Date.now(),
    role: "assistant",
    content: reverted.length
      ? `Undone. I restored ${reverted.length} field${reverted.length > 1 ? "s" : ""}${names ? ` (${names}${reverted.length > 4 ? ", …" : ""})` : ""}.`
      : "Undone.",
    meta: { icon: "success" },
  });
}

function labelMap(s) {
  return Object.fromEntries((s.registry?.fields || []).map((f) => [f.key, f.label]));
}

// ---------------------------------------------------------------- thunks
export const fetchFields = createAsyncThunk("deviation/fetchFields", async (_, { rejectWithValue }) => {
  try {
    return await api.fields();
  } catch (e) {
    return rejectWithValue(errorMessage(e));
  }
});

export const fetchDeviations = createAsyncThunk("deviation/fetchDeviations", async (_, { rejectWithValue }) => {
  try {
    return await api.listDeviations();
  } catch (e) {
    return rejectWithValue(errorMessage(e));
  }
});

export const fetchAudit = createAsyncThunk("deviation/fetchAudit", async (id, { rejectWithValue }) => {
  try {
    return { id, rows: await api.audit(id) };
  } catch (e) {
    return rejectWithValue(errorMessage(e));
  }
});

export const saveDeviation = createAsyncThunk(
  "deviation/save",
  async (_, { getState, dispatch, rejectWithValue }) => {
    const { form, userOverrides, changeLog, currentId } = getState().deviation;
    const body = { form, user_overrides: userOverrides, changes: changeLog };
    try {
      const saved = currentId ? await api.updateDeviation(currentId, body) : await api.createDeviation(body);
      dispatch(fetchDeviations());
      return { saved, created: !currentId };
    } catch (e) {
      return rejectWithValue(errorMessage(e));
    }
  }
);

export const loadDeviation = createAsyncThunk("deviation/load", async (id, { rejectWithValue }) => {
  try {
    return await api.getDeviation(id);
  } catch (e) {
    return rejectWithValue(errorMessage(e));
  }
});

export const deleteDeviation = createAsyncThunk("deviation/delete", async (id, { dispatch, rejectWithValue }) => {
  try {
    await api.deleteDeviation(id);
    dispatch(fetchDeviations());
    return id;
  } catch (e) {
    return rejectWithValue(errorMessage(e));
  }
});

/** Send a chat message (and optional file) to the LangGraph agent. */
export const sendChat = createAsyncThunk(
  "deviation/sendChat",
  async ({ message, file }, { getState, dispatch, rejectWithValue }) => {
    const { form, userOverrides, messages } = getState().deviation;
    const history = messages.slice(1).map(({ role, content }) => ({ role, content }));
    try {
      const res = await api.chat({ message, file, form, history, userOverrides });
      // The agent only signals "save"; the client performs it so the same Save path is used everywhere.
      if (res.action === "save") setTimeout(() => dispatch(saveDeviation()), 0);
      return res;
    } catch (e) {
      return rejectWithValue(errorMessage(e));
    }
  }
);

// ---------------------------------------------------------------- slice
const slice = createSlice({
  name: "deviation",
  initialState,
  reducers: {
    undo(state) {
      undoLast(state, labelMap(state));
    },
    newDeviation(state) {
      Object.assign(state, {
        past: [],
        form: {}, userOverrides: {}, changeLog: [], currentId: null, dirty: false,
        highlight: { fields: [], token: state.highlight.token + 1 },
        copilotStatus: "idle",
        messages: [...state.messages, { at: Date.now(), role: "assistant", content: "Started a new, blank report.", meta: { icon: "info" } }],
      });
    },
    closeAudit(state) {
      state.audit.open = false;
    },
    clearNotice(state) {
      state.notice = null;
      state.error = null;
    },
  },
  extraReducers: (b) => {
    b.addCase(fetchFields.fulfilled, (s, { payload }) => {
      s.registry = { sections: payload.sections, riskSection: payload.risk_section, fields: payload.fields, tiers: payload.tiers };
      s.mockMode = payload.mock_mode;
      s.model = payload.model;
    });
    b.addCase(fetchFields.rejected, (s, { payload }) => {
      s.error = payload;
    });

    // --- chat
    b.addCase(sendChat.pending, (s, { meta }) => {
      s.loading = true;
      s.error = null;
      const { message, file } = meta.arg;
      s.copilotStatus = "working";
      // Only the file's name/type is stored (a File object is not serializable).
      s.messages.push({ at: Date.now(), role: "user", content: message, file: file ? { name: file.name, kind: fileKind(file.name) } : null });
    });
    b.addCase(sendChat.fulfilled, (s, { payload: r }) => {
      s.loading = false;
      s.mockMode = r.mock_mode;
      s.copilotStatus = r.errors.length ? "idle" : "done";
      if (r.action === "undo") {
        undoLast(s, labelMap(s));
        return;
      }
      if (r.changes.length || r.action === "reset") {
        s.past.push(snapshot(s));
        if (s.past.length > UNDO_LIMIT) s.past.shift();
      }
      if (r.action === "reset") {
        Object.assign(s, { form: {}, userOverrides: {}, changeLog: [], currentId: null, dirty: false });
      } else {
        s.form = r.form;
        s.userOverrides = r.user_overrides;
        // A new "log" starts a new deviation, so earlier (unsaved) history no longer applies.
        if (r.intent === "log") Object.assign(s, { changeLog: [], currentId: null });
        s.changeLog.push(...r.changes);
        if (r.changes.length) s.dirty = true;
      }
      s.highlight = { fields: r.changes.map((c) => c.field), token: s.highlight.token + 1 };
      s.messages.push({
        at: Date.now(),
        role: "assistant",
        content: r.reply,
        meta: {
          intent: r.intent,
          icon: ["off_topic", "rejected"].includes(r.intent) ? "guard"
            : r.errors.length ? "info" : r.changes.length || r.action ? "success" : "info",
          toolsUsed: r.tools_used,
          changes: r.changes,
          extractionMethod: r.extraction_method,
          preview: r.extracted_text_preview,
          errors: r.errors,
        },
      });
    });
    b.addCase(sendChat.rejected, (s, { payload, error }) => {
      s.loading = false;
      s.copilotStatus = "idle";
      s.error = payload || error.message;
      s.messages.push({ at: Date.now(), role: "assistant", content: `⚠ ${s.error}`, meta: { isError: true } });
    });

    // --- save / load / list
    b.addCase(saveDeviation.pending, (s) => {
      s.saving = true;
      s.error = null;
    });
    b.addCase(saveDeviation.fulfilled, (s, { payload: { saved, created } }) => {
      s.saving = false;
      s.form = saved.form;
      s.userOverrides = saved.user_overrides;
      s.currentId = saved.form.deviation_id;
      s.changeLog = [];
      s.dirty = false;
      s.past = []; // committed values are in the ledger; further corrections go through chat + audit
      s.highlight = { fields: created ? ["deviation_id", "date_reported", "last_updated_by"] : [], token: s.highlight.token + 1 };
      const msg = `${created ? "Saved" : "Updated"} ${saved.form.deviation_id}. The change history has been recorded.`;
      s.notice = msg;
      s.copilotStatus = "done";
      s.messages.push({ at: Date.now(), role: "assistant", content: msg, meta: { icon: "success" } });
    });
    b.addCase(saveDeviation.rejected, (s, { payload }) => {
      s.saving = false;
      s.error = payload;
      s.messages.push({ at: Date.now(), role: "assistant", content: `⚠ Save failed: ${payload}`, meta: { isError: true } });
    });
    b.addCase(fetchDeviations.fulfilled, (s, { payload }) => {
      s.savedList = payload;
    });
    b.addCase(loadDeviation.fulfilled, (s, { payload }) => {
      s.past = [];
      s.form = payload.form;
      s.userOverrides = payload.user_overrides;
      s.currentId = payload.form.deviation_id;
      s.changeLog = [];
      s.dirty = false;
      s.highlight = { fields: [], token: s.highlight.token + 1 };
      s.messages.push({
        at: Date.now(),
        role: "assistant",
        content: `Loaded ${payload.form.deviation_id}. Tell me what to change, then save to update it.`,
        meta: { icon: "info" },
      });
    });
    b.addCase(loadDeviation.rejected, (s, { payload }) => {
      s.error = payload;
    });
    b.addCase(fetchAudit.fulfilled, (s, { payload }) => {
      s.audit = { ...payload, open: true };
    });
    b.addCase(fetchAudit.rejected, (s, { payload }) => {
      s.error = payload;
    });
    b.addCase(deleteDeviation.fulfilled, (s, { payload: id }) => {
      if (s.currentId === id) {
        Object.assign(s, { form: {}, userOverrides: {}, currentId: null, changeLog: [], dirty: false, past: [] });
        s.highlight = { fields: [], token: s.highlight.token + 1 };
      }
      s.notice = `Deleted ${id}.`;
    });
  },
});

export const { newDeviation, clearNotice, closeAudit, undo } = slice.actions;
export default slice.reducer;
