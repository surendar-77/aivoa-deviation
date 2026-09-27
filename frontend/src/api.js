// Axios client for the FastAPI backend. All HTTP lives here so components stay presentational.
import axios from "axios";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000/api",
  timeout: 120000, // LLM + OCR calls can take a while
});

/** Turn any axios error into one readable sentence for the UI. */
export function errorMessage(err) {
  if (err.response?.data?.detail) {
    const d = err.response.data.detail;
    return typeof d === "string" ? d : JSON.stringify(d);
  }
  if (err.code === "ERR_NETWORK") return "Cannot reach the backend at localhost:8000 - is it running?";
  return err.message || "Unexpected error";
}

export const api = {
  health: () => client.get("/health").then((r) => r.data),
  fields: () => client.get("/fields").then((r) => r.data),

  /** Multipart: a file may be attached; form/history/overrides travel as JSON strings. */
  chat: ({ message, file, form, history, userOverrides }) => {
    const data = new FormData();
    data.append("message", message || "");
    data.append("form", JSON.stringify(form || {}));
    data.append("history", JSON.stringify(history || []));
    data.append("user_overrides", JSON.stringify(userOverrides || {}));
    if (file) data.append("file", file);
    return client.post("/ai/chat", data).then((r) => r.data);
  },

  /** Voice input: a recorded clip -> { text } (Groq Whisper). The caller puts the text in the chat box for review. */
  transcribe: (blob, filename) => {
    const data = new FormData();
    data.append("audio", blob, filename);
    return client.post("/ai/transcribe", data, { timeout: 60000 }).then((r) => r.data);
  },

  listDeviations: () => client.get("/deviations").then((r) => r.data),
  getDeviation: (id) => client.get(`/deviations/${id}`).then((r) => r.data),
  createDeviation: (body) => client.post("/deviations", body).then((r) => r.data),
  updateDeviation: (id, body) => client.put(`/deviations/${id}`, body).then((r) => r.data),
  deleteDeviation: (id) => client.delete(`/deviations/${id}`),
  audit: (id) => client.get(`/deviations/${id}/audit`).then((r) => r.data),
};
