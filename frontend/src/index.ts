import { serve } from "bun";
import index from "./index.html";

// The UI calls /api/*; this server forwards it to the FastAPI backend, so the browser never needs CORS.
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

const server = serve({
  routes: {
    "/api/*": async (req) => {
      const url = new URL(req.url);
      const target = API_URL + url.pathname.replace(/^\/api/, "") + url.search;
      try {
        return await fetch(target, { method: req.method, headers: req.headers, body: req.body });
      } catch {
        return Response.json({ detail: `Backend not reachable at ${API_URL}` }, { status: 502 });
      }
    },
    "/*": index,
  },

  development: process.env.NODE_ENV !== "production" && { hmr: true, console: true },
});

console.log(`Porters decision workbench at ${server.url}`);
