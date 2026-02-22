const threadIdEl = document.getElementById("thread-id");
const newThreadBtn = document.getElementById("new-thread");
const stageBadge = document.getElementById("badge-stage");
const intentBadge = document.getElementById("badge-intent");
const interesseBadge = document.getElementById("badge-interesse");
const promptBadge = document.getElementById("badge-prompt");
const chatLog = document.getElementById("chat-log");
const form = document.getElementById("chat-form");
const input = document.getElementById("chat-input");
const clinicInput = document.getElementById("clinic-id");
const sendBtn = document.getElementById("send-btn");
const endpoint = form.dataset.endpoint || "/api/chat/test";

function generateThreadId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }
  return "thread-" + Date.now() + "-" + Math.floor(Math.random() * 10000);
}

const state = {
  threadId: generateThreadId(),
  sending: false,
  typingNode: null,
};

function setThread(threadId) {
  state.threadId = threadId;
  threadIdEl.textContent = threadId;
}

function setBadges({ stage = "-", intent = "-", interesse = "-", prompt_profile = "-" }) {
  stageBadge.textContent = "stage: " + stage;
  intentBadge.textContent = "intent: " + intent;
  interesseBadge.textContent = "interesse: " + interesse;
  promptBadge.textContent = "prompt: " + prompt_profile;
}

function addMessage(role, text) {
  const wrapper = document.createElement("article");
  wrapper.className = "message " + (role === "user" ? "message-user" : "message-bot");

  const label = document.createElement("strong");
  label.textContent = role === "user" ? "Voce" : "Agente";

  const body = document.createElement("p");
  body.textContent = text;
  body.style.margin = "0";
  body.style.lineHeight = "1.45";

  wrapper.appendChild(label);
  wrapper.appendChild(body);
  chatLog.appendChild(wrapper);
  chatLog.scrollTop = chatLog.scrollHeight;
  return wrapper;
}

function showTyping() {
  const wrapper = document.createElement("article");
  wrapper.className = "message message-bot";

  const label = document.createElement("strong");
  label.textContent = "Agente";
  wrapper.appendChild(label);

  const typing = document.createElement("div");
  typing.className = "typing";
  typing.innerHTML = "<span></span><span></span><span></span>";
  wrapper.appendChild(typing);

  chatLog.appendChild(wrapper);
  chatLog.scrollTop = chatLog.scrollHeight;
  state.typingNode = wrapper;
}

function hideTyping() {
  if (state.typingNode && state.typingNode.parentNode) {
    state.typingNode.parentNode.removeChild(state.typingNode);
  }
  state.typingNode = null;
}

async function sendMessage(message) {
  if (state.sending) {
    return;
  }

  state.sending = true;
  sendBtn.disabled = true;
  addMessage("user", message);
  showTyping();

  try {
    const payload = {
      message,
      thread_id: state.threadId,
    };
    const clinic = clinicInput.value.trim();
    if (clinic) {
      payload.clinic_id = clinic;
    }

    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error("HTTP " + response.status);
    }

    const data = await response.json();
    hideTyping();
    setThread(data.thread_id || state.threadId);
    setBadges({
      stage: data.stage,
      intent: data.intent,
      interesse: data.interesse,
      prompt_profile: data.prompt_profile,
    });
    addMessage("bot", data.response || "Sem resposta.");
  } catch (error) {
    hideTyping();
    addMessage("bot", "Falha ao chamar o endpoint de chat. Verifique se a API esta rodando.");
    console.error(error);
  } finally {
    state.sending = false;
    sendBtn.disabled = false;
  }
}

function resetConversation() {
  chatLog.innerHTML = "";
  setThread(generateThreadId());
  setBadges({});
  addMessage(
    "bot",
    "Conversa reiniciada. Eu sou o agente SDR. Me conte seu nome e o motivo da consulta."
  );
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) {
    return;
  }
  input.value = "";
  await sendMessage(message);
});

newThreadBtn.addEventListener("click", resetConversation);

setThread(state.threadId);
setBadges({});
addMessage("bot", "Pronto para testar. Envie sua primeira mensagem.");
