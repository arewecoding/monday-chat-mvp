<script>
  import { marked } from "marked";
  // --- State ---
  let messages = []; // { role: "user"|"assistant", content: string }[]
  let actionLog = []; // { tool, args, status: "running"|"done", summary }[]
  let isLoading = false;
  let input = "";
  let chatEl; // ref to scroll the chat panel

  // Read backend URL from build-time env var (set in Vercel dashboard)
  const API_URL = import.meta.env.PUBLIC_API_URL || "http://localhost:8000";

  // Monday.com board link — visible in the header for evaluators
  const MONDAY_BOARD_URL = "https://rushi-v.monday.com/boards/";

  // --- Welcome message shown on load ---
  const WELCOME = `👋 Hi! I'm your BI agent connected to your Monday.com boards.

Ask me anything about your business — pipeline health, deal stages, sector performance,
billing, work order status, team performance, or cross-board analysis.

**Example questions:**
• How's our Renewables pipeline looking?
• What's our overall win rate?
• Show me stuck or overdue work orders.
• Which deals are closest to closing?`;

  // --- Reset conversation ---
  function resetChat() {
    messages = [];
    actionLog = [];
    input = "";
    isLoading = false;
  }

  // --- Send a message ---
  async function sendMessage() {
    if (!input.trim() || isLoading) return;

    const userText = input.trim();
    input = "";
    isLoading = true;

    // Add user message to chat
    messages = [...messages, { role: "user", content: userText }];
    // Clear action log for this new query
    actionLog = [];

    // Scroll chat to bottom
    setTimeout(scrollChat, 50);

    try {
      const response = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        // Accumulate decoded bytes (chunks can split mid-line)
        buffer += decoder.decode(value, { stream: true });

        // Process every complete line in the buffer
        const lines = buffer.split("\n");
        buffer = lines.pop(); // keep the incomplete last line

        for (const line of lines) {
          if (!line.trim()) continue;

          let event;
          try {
            event = JSON.parse(line);
          } catch {
            continue; // skip malformed line
          }

          if (event.type === "tool_start") {
            actionLog = [
              ...actionLog,
              {
                tool: event.tool,
                args: event.args,
                status: "running",
                summary: "",
              },
            ];
          } else if (event.type === "tool_done") {
            // Update the most recent matching tool entry
            actionLog = actionLog.map((entry, i) => {
              if (entry.tool === event.tool && entry.status === "running") {
                return { ...entry, status: "done", summary: event.summary };
              }
              return entry;
            });
          } else if (event.type === "answer") {
            messages = [
              ...messages,
              { role: "assistant", content: event.content },
            ];
            setTimeout(scrollChat, 50);
          }
        }
      }
    } catch (err) {
      messages = [
        ...messages,
        {
          role: "assistant",
          content: `⚠️ Error: ${err.message}. Check that the backend is running and your API keys are set.`,
        },
      ];
    }

    isLoading = false;
  }

  function scrollChat() {
    if (chatEl) chatEl.scrollTop = chatEl.scrollHeight;
  }

  function handleKeydown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  // Format args for display in the action log
  function formatArgs(args) {
    if (!args) return "";
    const parts = [];
    if (args.board_id) parts.push(`board: ${args.board_id}`);
    if (args.column_id) parts.push(`col: ${args.column_id}`);
    if (args.value) parts.push(`"${args.value}"`);
    if (args.column_ids) parts.push(`${args.column_ids.length} cols`);
    return parts.join(", ");
  }
</script>

<!-- ═══════════════════════ MARKUP ═══════════════════════ -->
<div class="shell">
  <!-- Header -->
  <header>
    <div class="header-left">
      <div class="logo-icon">📊</div>
      <div>
        <h1>BI Agent</h1>
        <p>Live Monday.com Intelligence</p>
      </div>
    </div>
    <div class="header-right">
      <button
        class="reset-btn"
        id="reset-chat-btn"
        on:click={resetChat}
        title="Clear conversation"
        disabled={isLoading}
      >
        🗑 Reset Chat
      </button>
      <a
        href={MONDAY_BOARD_URL}
        target="_blank"
        rel="noopener noreferrer"
        class="board-link"
        id="monday-board-link"
      >
        📋 View Monday Board →
      </a>
    </div>
  </header>

  <main>
    <!-- Chat Panel -->
    <div class="chat-panel">
      <div class="chat-messages" bind:this={chatEl}>
        <!-- Welcome message -->
        {#if messages.length === 0}
          <div class="welcome">{WELCOME}</div>
        {/if}

        <!-- Conversation -->
        {#each messages as msg (msg)}
          {#if msg.role === "assistant"}
            <div class="bubble assistant">{@html marked(msg.content)}</div>
          {:else}
            <div class="bubble user">{msg.content}</div>
          {/if}
        {/each}

        <!-- Loading indicator -->
        {#if isLoading}
          <div class="typing">
            <span></span><span></span><span></span>
          </div>
        {/if}
      </div>

      <!-- Input bar -->
      <div class="chat-input">
        <textarea
          id="chat-input"
          placeholder="Ask a business question..."
          bind:value={input}
          on:keydown={handleKeydown}
          rows="1"
          disabled={isLoading}
        ></textarea>
        <button
          class="send"
          id="send-btn"
          on:click={sendMessage}
          disabled={isLoading || !input.trim()}
        >
          {isLoading ? "..." : "Send"}
        </button>
      </div>
    </div>

    <!-- Action Log Panel -->
    <div class="log-panel">
      <div class="log-header">
        <h2>Action Log</h2>
        <p>Live Monday.com API calls</p>
      </div>
      <div class="log-entries">
        {#if actionLog.length === 0}
          <p class="log-empty">
            Tool calls will appear here<br />as the agent queries Monday.com
          </p>
        {:else}
          {#each actionLog as entry}
            <div class="log-entry {entry.status}">
              <div class="log-entry-header">
                <div class="status-dot {entry.status}"></div>
                <span class="tool-name">{entry.tool}</span>
                <span class="status-badge {entry.status}">
                  {entry.status === "running" ? "calling" : "done"}
                </span>
              </div>
              {#if entry.args}
                <div class="log-args">{formatArgs(entry.args)}</div>
              {/if}
              {#if entry.summary}
                <div class="log-summary">↳ {entry.summary}</div>
              {/if}
            </div>
          {/each}
        {/if}
      </div>
    </div>
  </main>
</div>

<!-- ═══════════════════════ STYLES ═══════════════════════ -->
<style>
  :global(*, *::before, *::after) {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }

  :global(body) {
    font-family:
      "Inter",
      -apple-system,
      BlinkMacSystemFont,
      "Segoe UI",
      sans-serif;
    background: #0f1117;
    color: #e2e8f0;
    height: 100vh;
    overflow: hidden;
  }

  /* ── Layout ── */
  .shell {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }

  /* ── Header ── */
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 24px;
    height: 56px;
    background: #16181f;
    border-bottom: 1px solid #2d3142;
    flex-shrink: 0;
    gap: 12px;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .logo-icon {
    width: 32px;
    height: 32px;
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    flex-shrink: 0;
  }

  header h1 {
    font-size: 15px;
    font-weight: 600;
    color: #f1f5f9;
    letter-spacing: -0.01em;
  }

  header p {
    font-size: 12px;
    color: #64748b;
  }

  .board-link {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    background: #1e2130;
    border: 1px solid #2d3142;
    border-radius: 8px;
    color: #94a3b8;
    text-decoration: none;
    font-size: 13px;
    font-weight: 500;
    transition: all 0.15s ease;
    white-space: nowrap;
  }

  .board-link:hover {
    background: #252840;
    color: #c4b5fd;
    border-color: #6366f1;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }

  .reset-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    background: transparent;
    border: 1px solid #2d3142;
    border-radius: 8px;
    color: #64748b;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
    white-space: nowrap;
  }

  .reset-btn:hover:not(:disabled) {
    background: #2d1a1a;
    color: #f87171;
    border-color: #7f1d1d;
  }

  .reset-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  /* ── Main: two panels ── */
  main {
    display: flex;
    flex: 1;
    overflow: hidden;
  }

  /* ── Chat Panel ── */
  .chat-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    border-right: 1px solid #2d3142;
  }

  .chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .chat-messages::-webkit-scrollbar {
    width: 4px;
  }
  .chat-messages::-webkit-scrollbar-track {
    background: transparent;
  }
  .chat-messages::-webkit-scrollbar-thumb {
    background: #2d3142;
    border-radius: 4px;
  }

  /* Bubble */
  .bubble {
    max-width: 82%;
    padding: 12px 16px;
    border-radius: 12px;
    font-size: 14px;
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .bubble.user {
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    color: #fff;
    align-self: flex-end;
    border-bottom-right-radius: 4px;
  }

  .bubble.assistant {
    background: #1e2130;
    color: #e2e8f0;
    align-self: flex-start;
    border-bottom-left-radius: 4px;
    border: 1px solid #2d3142;
  }

  /* Welcome */
  .welcome {
    background: linear-gradient(135deg, #1a1d2e, #1e2130);
    border: 1px solid #2d3142;
    border-radius: 12px;
    padding: 20px;
    color: #94a3b8;
    font-size: 14px;
    line-height: 1.7;
    white-space: pre-wrap;
    align-self: flex-start;
    max-width: 82%;
  }

  .welcome strong {
    color: #c4b5fd;
    font-weight: 600;
  }

  /* Loading dots */
  .typing {
    display: flex;
    gap: 4px;
    padding: 14px 16px;
    background: #1e2130;
    border: 1px solid #2d3142;
    border-radius: 12px;
    border-bottom-left-radius: 4px;
    align-self: flex-start;
  }

  .typing span {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #6366f1;
    animation: bounce 1.2s infinite ease-in-out;
  }
  .typing span:nth-child(2) {
    animation-delay: 0.2s;
  }
  .typing span:nth-child(3) {
    animation-delay: 0.4s;
  }

  @keyframes bounce {
    0%,
    60%,
    100% {
      transform: translateY(0);
      opacity: 0.5;
    }
    30% {
      transform: translateY(-6px);
      opacity: 1;
    }
  }

  /* ── Chat Input ── */
  .chat-input {
    padding: 16px 24px;
    background: #16181f;
    border-top: 1px solid #2d3142;
    display: flex;
    gap: 10px;
    align-items: flex-end;
  }

  textarea {
    flex: 1;
    background: #1e2130;
    border: 1px solid #2d3142;
    border-radius: 10px;
    color: #e2e8f0;
    font-family: inherit;
    font-size: 14px;
    padding: 10px 14px;
    resize: none;
    min-height: 42px;
    max-height: 120px;
    line-height: 1.5;
    outline: none;
    transition: border-color 0.15s;
  }

  textarea:focus {
    border-color: #6366f1;
  }

  textarea::placeholder {
    color: #475569;
  }

  button.send {
    height: 42px;
    padding: 0 18px;
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    color: #fff;
    border: none;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition:
      opacity 0.15s,
      transform 0.1s;
    white-space: nowrap;
  }

  button.send:hover:not(:disabled) {
    opacity: 0.9;
    transform: translateY(-1px);
  }

  button.send:disabled {
    opacity: 0.45;
    cursor: not-allowed;
    transform: none;
  }

  /* ── Action Log Panel ── */
  .log-panel {
    width: 300px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    background: #13151e;
  }

  .log-header {
    padding: 16px 20px 12px;
    border-bottom: 1px solid #2d3142;
    flex-shrink: 0;
  }

  .log-header h2 {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #475569;
  }

  .log-header p {
    font-size: 11px;
    color: #334155;
    margin-top: 2px;
  }

  .log-entries {
    flex: 1;
    overflow-y: auto;
    padding: 12px 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .log-entries::-webkit-scrollbar {
    width: 3px;
  }
  .log-entries::-webkit-scrollbar-track {
    background: transparent;
  }
  .log-entries::-webkit-scrollbar-thumb {
    background: #2d3142;
    border-radius: 4px;
  }

  .log-empty {
    color: #334155;
    font-size: 12px;
    text-align: center;
    margin-top: 24px;
    line-height: 1.6;
  }

  .log-entry {
    background: #1a1d2a;
    border: 1px solid #2d3142;
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 12px;
    transition: border-color 0.2s;
  }

  .log-entry.running {
    border-color: #f59e0b;
    animation: pulse-border 1.5s infinite;
  }

  .log-entry.done {
    border-color: #22c55e40;
  }

  @keyframes pulse-border {
    0%,
    100% {
      border-color: #f59e0b60;
    }
    50% {
      border-color: #f59e0b;
    }
  }

  .log-entry-header {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .status-dot.running {
    background: #f59e0b;
    animation: pulse-dot 1s infinite;
  }

  .status-dot.done {
    background: #22c55e;
  }

  @keyframes pulse-dot {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.3;
    }
  }

  .tool-name {
    font-weight: 600;
    color: #c4b5fd;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .status-badge {
    font-size: 10px;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 4px;
    flex-shrink: 0;
  }

  .status-badge.running {
    background: #f59e0b20;
    color: #f59e0b;
  }

  .status-badge.done {
    background: #22c55e20;
    color: #22c55e;
  }

  .log-args {
    color: #475569;
    margin-top: 4px;
    font-family: "SF Mono", "Fira Code", monospace;
    font-size: 10px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .log-summary {
    color: #64748b;
    margin-top: 4px;
    font-size: 11px;
  }
</style>
