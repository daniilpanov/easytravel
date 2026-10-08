<template>
  <main class="chat">
    <h1>EasyTravel chat (MVP-1)</h1>
    <div class="sessions">
      <button @click="newChat">New chat</button>
      <select v-model="sessionId" @change="loadHistory">
        <option :value="null">Current chat</option>
        <option v-for="s in sessions" :key="s.id" :value="s.id">
          {{ s.title }}
        </option>
      </select>
    </div>
    <ul>
      <li v-for="(m, i) in messages" :key="i">
        <strong>{{ m.role }}:</strong> {{ m.text }}
      </li>
    </ul>
    <form @submit.prevent="send">
      <input v-model="draft" placeholder="Where to?" />
      <button type="submit">Send</button>
    </form>
  </main>
</template>

<script setup>
import { onMounted, ref } from "vue";

const messages = ref([]);
const draft = ref("");
const sessionId = ref(null);
const sessions = ref([]);

async function refreshSessions() {
  const res = await fetch("/api/sessions");
  const data = await res.json();
  sessions.value = data.sessions;
}

async function loadHistory() {
  if (!sessionId.value) {
    messages.value = [];
    return;
  }
  const res = await fetch(`/api/history/${sessionId.value}`);
  const data = await res.json();
  messages.value = data.messages;
}

function newChat() {
  sessionId.value = null;
  messages.value = [];
  localStorage.removeItem("easytravel_session");
}

async function send() {
  const text = draft.value.trim();
  if (!text) return;
  messages.value.push({ role: "user", text });
  draft.value = "";
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text, session_id: sessionId.value }),
  });
  const data = await res.json();
  sessionId.value = data.session_id;
  localStorage.setItem("easytravel_session", String(data.session_id));
  messages.value.push({ role: "assistant", text: data.reply });
  await refreshSessions();
}

onMounted(async () => {
  const saved = localStorage.getItem("easytravel_session");
  if (saved) sessionId.value = Number(saved);
  await refreshSessions();
  await loadHistory();
});
</script>

<style>
.chat {
  max-width: 640px;
  margin: 2rem auto;
  font-family: sans-serif;
}
.sessions {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
}
</style>
