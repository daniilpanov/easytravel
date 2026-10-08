<template>
  <main class="chat">
    <h1>EasyTravel chat (MVP-1)</h1>
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
import { ref } from "vue";

const messages = ref([]);
const draft = ref("");

async function send() {
  const text = draft.value.trim();
  if (!text) return;
  messages.value.push({ role: "user", text });
  draft.value = "";
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text }),
  });
  const data = await res.json();
  messages.value.push({ role: "assistant", text: data.reply });
}
</script>

<style>
.chat {
  max-width: 640px;
  margin: 2rem auto;
  font-family: sans-serif;
}
</style>
