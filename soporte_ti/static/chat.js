function iniciarChat({ url, rolPropio, caja, form, onResuelta }) {
  const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + url);
  const campo = form.querySelector("input");
  const pintar = (m) => {
    const d = document.createElement("div");
    d.className = "burbuja " + (m.rol === rolPropio ? "mia" : "");
    const a = document.createElement("small");
    a.textContent = m.autor;
    const t = document.createElement("span");
    t.textContent = m.texto;
    d.append(a, t);
    caja.appendChild(d);
    caja.scrollTop = caja.scrollHeight;
  };
  ws.onmessage = (ev) => {
    const d = JSON.parse(ev.data);
    if (d.tipo === "historial") { caja.innerHTML = ""; d.mensajes.forEach(pintar); }
    else if (d.tipo === "mensaje") pintar(d);
    else if (d.tipo === "resuelta") {
    campo.disabled = true;
    form.querySelector("button").disabled = true;
    if (onResuelta) onResuelta();
}
  };
  form.onsubmit = (e) => {
    e.preventDefault();
    const t = campo.value.trim();
    if (t && ws.readyState === 1) { ws.send(t); campo.value = ""; }
  };
  return ws;
}