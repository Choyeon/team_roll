/* Realtime channel for one activity: snapshot frames, heartbeat, backoff reconnect. */

const HEARTBEAT_MS = 25000;
const MAX_BACKOFF_MS = 15000;

export function openActivitySocket(activityId, { onMessage, onStatus } = {}) {
  let socket = null;
  let heartbeat = null;
  let retry = null;
  let attempt = 0;
  let closed = false;

  function setStatus(value) {
    onStatus?.(value);
  }

  function scheduleReconnect() {
    if (closed) return;
    const delay = Math.min(MAX_BACKOFF_MS, 500 * 2 ** attempt);
    attempt += 1;
    retry = setTimeout(connect, delay);
  }

  function connect() {
    if (closed) return;
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    setStatus("connecting");
    try {
      socket = new WebSocket(`${scheme}://${window.location.host}/ws/${encodeURIComponent(activityId)}`);
    } catch {
      setStatus("offline");
      scheduleReconnect();
      return;
    }

    socket.addEventListener("open", () => {
      attempt = 0;
      setStatus("online");
      heartbeat = setInterval(() => {
        if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "ping" }));
      }, HEARTBEAT_MS);
    });

    socket.addEventListener("message", (event) => {
      let frame;
      try {
        frame = JSON.parse(event.data);
      } catch {
        return; // a malformed frame is not worth dropping the room over
      }
      onMessage?.(frame);
    });

    socket.addEventListener("close", () => {
      clearInterval(heartbeat);
      heartbeat = null;
      if (closed) return;
      setStatus("offline");
      scheduleReconnect();
    });

    socket.addEventListener("error", () => socket?.close());
  }

  connect();

  return {
    close() {
      closed = true;
      clearTimeout(retry);
      clearInterval(heartbeat);
      socket?.close();
      socket = null;
    },
  };
}
