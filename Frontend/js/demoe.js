(() => {
  const root = document.createElement("div");
  root.id = "demoe-root";
  root.innerHTML = `<button class="demoe-launcher" type="button" aria-label="Open DEMOE AI Assistant" aria-expanded="false" aria-controls="demoe-panel"><img src="/assets/images/demoe-avatar.svg" alt="" aria-hidden="true"></button>
    <section class="demoe-panel" id="demoe-panel" role="dialog" aria-label="DEMOE AI Help Assistant" aria-hidden="true">
      <header class="demoe-header"><span class="demoe-avatar"><img src="/assets/images/demoe-avatar.svg" alt="" aria-hidden="true"></span><span class="demoe-title">DEMOE <small>DM Skill Institute AI help</small></span><button class="demoe-close" type="button" aria-label="Close DEMOE">×</button></header>
      <div class="demoe-messages" role="log" aria-live="polite" aria-label="Chat messages"></div>
      <p class="demoe-notice">DEMOE uses AI. Please don't share passwords, OTPs or payment details.</p>
      <form class="demoe-form"><textarea class="demoe-input" rows="1" maxlength="4000" aria-label="Type your question" placeholder="Type your question..."></textarea><button class="demoe-send" type="submit" aria-label="Send message">➤</button></form>
    </section>`;
  document.body.append(root);
  const launcher = root.querySelector(".demoe-launcher");
  const panel = root.querySelector(".demoe-panel");
  const close = root.querySelector(".demoe-close");
  const messages = root.querySelector(".demoe-messages");
  const form = root.querySelector(".demoe-form");
  const input = root.querySelector(".demoe-input");
  const send = root.querySelector(".demoe-send");
  const history = []; // Only in this page's memory; never persisted.
  let busy = false;
  let started = false;
  const fallback =
    "Sorry, I'm unable to connect right now. Please try again or contact DM Skill Institute.";

  function addMessage(text, sender, extraClass = "") {
    const el = document.createElement("div");
    el.className = `demoe-message ${sender === "user" ? "demoe-user" : ""} ${extraClass}`;
    el.textContent = text; // Never interpret AI/user content as HTML.
    messages.append(el);
    messages.scrollTop = messages.scrollHeight;
    return el;
  }
  function setBusy(value) {
    busy = value;
    send.disabled = value;
    root.querySelectorAll(".demoe-faqs button").forEach((button) => {
      button.disabled = value;
    });
  }
  async function ask(text) {
    const question = text.trim();
    if (!question || busy || question.length > 4000) return;
    input.value = "";
    addMessage(question, "user");
    setBusy(true);
    const typing = addMessage(
      "DEMOE is typing... ●",
      "assistant",
      "demoe-typing",
    );
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question, history: history.slice(-6) }),
      });
      const data = await response.json();
      const reply =
        response.ok && data.success && typeof data.reply === "string"
          ? data.reply
          : response.status === 429
            ? "Please wait a moment before sending another question."
            : fallback;
      typing.remove();
      addMessage(reply, "assistant");
      if (response.ok && data.success) {
        history.push(
          { role: "user", content: question },
          { role: "assistant", content: reply },
        );
        if (history.length > 6) history.splice(0, history.length - 6);
      }
    } catch (_) {
      typing.remove();
      addMessage(fallback, "assistant");
    } finally {
      setBusy(false);
      input.focus();
    }
  }
  async function welcome() {
    addMessage(
      "Hi! I'm DEMOE 🤖. How can I help you explore DM Skill Institute?",
      "assistant",
    );
    const faqBox = document.createElement("div");
    faqBox.className = "demoe-faqs";
    messages.append(faqBox);
    try {
      const response = await fetch("/api/chat/faqs");
      if (!response.ok) return;
      const data = await response.json();
      if (!Array.isArray(data.questions)) return;
      data.questions.forEach((question) => {
        if (typeof question !== "string") return;
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = question;
        button.addEventListener("click", () => ask(question));
        faqBox.append(button);
      });
    } catch (_) {
      /* Visitors can still type when the FAQ service is unavailable. */
    }
  }
  function toggle(open) {
    panel.classList.toggle("demoe-open", open);
    panel.setAttribute("aria-hidden", String(!open));
    launcher.setAttribute("aria-expanded", String(open));
    launcher.setAttribute(
      "aria-label",
      open ? "Close DEMOE AI Assistant" : "Open DEMOE AI Assistant",
    );
    if (open) {
      if (!started) {
        started = true;
        welcome();
      }
      input.focus();
    } else launcher.focus();
  }
  launcher.addEventListener("click", () =>
    toggle(!panel.classList.contains("demoe-open")),
  );
  close.addEventListener("click", () => toggle(false));
  panel.addEventListener("keydown", (e) => {
    if (e.key === "Escape") toggle(false);
  });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    ask(input.value);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });
})();
