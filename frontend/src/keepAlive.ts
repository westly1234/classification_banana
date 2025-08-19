import api from "./components/api";

let timer: number | undefined;

export function startKeepAlive() {
  stopKeepAlive();
  timer = window.setInterval(() => {
    api.get("/ping", { params: { ts: Date.now() }, timeout: 6000 })
       .catch(() => {});
  }, 180_000); // 3분
}

export function stopKeepAlive() {
  if (timer) {
    clearInterval(timer);
    timer = undefined;
  }
}