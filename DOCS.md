# Forbin Technical Documentation

This document provides a detailed look at how Forbin works under the hood, its connection logic, and its user interface components.

## How It Works

### Why Forbin Probes the Health Endpoint

When `MCP_HEALTH_URL` is configured, Forbin probes that endpoint before opening an MCP connection. The probe serves **two purposes**:

1. **Availability check** — confirms the server is reachable and ready to accept traffic, similar to hitting an LLM provider's `/models` endpoint to verify the API is up before issuing real requests.
2. **Wake-up trigger** — on platforms that suspend or stop idle instances (Fly.io scale-to-zero, Railway, Render, etc.), the probe also rouses the service. The same HTTP request that verifies "is it up?" is what *makes* it come up.

If `MCP_HEALTH_URL` is not configured, Forbin skips this step entirely and connects directly — appropriate for always-on servers and local development.

### Wake-Up Process

For servers with a configured health URL, Forbin follows a three-step sequence:

1. **Health Probe**
   - Polls `MCP_HEALTH_URL` until it returns HTTP 200.
   - **Limit:** 6 attempts with 5-second waits between them. Per-request timeout is 30 seconds, so the worst-case ceiling is significantly higher than the inter-attempt total.
   - On suspended platforms, this is what triggers the cold-start.

2. **Initialization Pause**
   - Once the health endpoint responds, Forbin waits **5 seconds**.
   - A health endpoint responding 200 doesn't guarantee the MCP server inside the container has finished its own startup. The pause covers that gap.

3. **Connection with Retry**
   - Opens the MCP connection with an `init_timeout` of **30 seconds**.
   - Retries up to **3 times** with 5-second waits between attempts.
   - Tool listing is bundled into the same retry attempt to avoid session-expiry races between connect and `list_tools`.

This sequence makes connections reliable even against cold-started servers that take significant time to become fully ready for MCP traffic.

---

## User Interface

### Step Indicators

Throughout the connection and execution process, Forbin displays step indicators to show progress.

| Color | Icon | Meaning |
|-------|------|---------|
| **Yellow** | > | **In Progress** - The current action is being performed. |
| **Green** | + | **Success** - The step completed successfully. |
| **Dim/Grey** | - | **Skip** - This step was skipped (e.g., wake-up skipped if no health URL). |

### Anytime Logging Toggle

Forbin includes a background listener that monitors for the **`v`** keypress.

- **Non-blocking:** You can toggle logging even while Forbin is waiting for a health check or establishing a connection.
- **Real-time unsuppression:** When logging is toggled **ON**, Forbin's `FilteredStderr` immediately stops suppressing typical MCP library warnings and errors, showing you full tracebacks and connection details.
- **Visual Feedback:** A notification will appear in the CLI whenever the logging state changes.

### Interactive Tool Browser

1. **Discovery:** Forbin lists all tools provided by the MCP server.
2. **Inspection:** Selecting a tool shows its description and parameter requirements.
3. **Execution:** Forbin prompts for each parameter, performing basic type validation:
   - **Strings:** Direct input.
   - **Booleans:** Accepts `true`, `false`, `y`, `n`, `1`, `0`.
   - **Numbers:** Parses integers and floats.
   - **Objects/Arrays:** Parses local JSON strings.

---

## Error Handling Details

- **Session termination errors:** FastMCP sometimes returns a 400 error when a session is closed. Forbin automatically suppresses these harmless warnings.
- **Connection retries:** Uses exponential backoff and fresh client instantiation for each retry to recover from transient network issues.
- **Timeout management:** Tuned timeouts for tool discovery (15s) and tool execution (600s).
