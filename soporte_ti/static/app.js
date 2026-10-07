const $ = (s) => document.querySelector(s);
let timerCaso = null;
const params = new URLSearchParams(location.search);


async function api(ruta, opciones = {}) {
  const r = await fetch(ruta, { ...opciones, headers: { "Content-Type": "application/json" } });
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof datos.detail === "string" ? datos.detail : "No se pudo completar la acción");
  return datos;
}

function esc(t) {
  const d = document.createElement("div");
  d.textContent = t ?? "";
  return d.innerHTML;
}

function iniciar() {
  const caso = JSON.parse(localStorage.getItem("caso") || "null");
  if (caso) {
    seguirCaso(caso);
  } else {
    $("#bloque-espera").hidden = true;
    $("#bloque-form").hidden = false;
    cargarListas();
  }
}

async function cargarListas() {
  try {
    const cats = await api("/api/categorias");
    $("#categoria").innerHTML = '<option value="">Selecciona una categoría</option>' +
      cats.map((c) => `<option value="${c.id}">${esc(c.nombre)}</option>`).join("");
  } catch (err) {
    $("#msg-sol").textContent = err.message;
  }
}

async function seguirCaso(caso) {
  $("#bloque-form").hidden = true;
  $("#bloque-espera").hidden = false;
  $("#pulso").hidden = false;
  $("#titulo-espera").textContent = "Solicitud enviada";
  $("#texto-espera").textContent = "En unos momentos lo atenderá uno de nuestros especialistas.";
  clearInterval(timerCaso);
  const actualizarEstado = async () => {
    try {
      const e = await api(`/api/solicitudes/${caso.id}/estado?codigo=${encodeURIComponent(caso.codigo)}`);
      if (e.estado !== "pendiente") {
        $("#pulso").hidden = true;
        $("#titulo-espera").textContent = e.estado === "resuelta" ? "Caso resuelto" : "Ya te están atendiendo";
        $("#texto-espera").textContent = e.estado === "resuelta"
          ? `${e.especialista} marcó tu solicitud como resuelta.`
          : `${e.especialista} tomó tu solicitud. Puedes escribirle aquí abajo.`;
        clearInterval(timerCaso);
        if (e.estado === "aceptada") abrirChat(caso);
      }
    } catch (_) {
      clearInterval(timerCaso);
      localStorage.removeItem("caso");
      iniciar();
    }
  };
  await actualizarEstado();
  timerCaso = setInterval(actualizarEstado, 5000);
}

$("#form-solicitud").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const btn = f.querySelector("button[type=submit]");
  btn.disabled = true;
  try {
    const d = await api("/api/solicitudes", {
      method: "POST",
           body: JSON.stringify({
        nombre: f.nombre.value,
        correo: f.correo.value,
        dependencia: f.dependencia.value,
        categoria_id: Number(f.categoria.value),
        observacion: f.observacion.value,
        equipo: params.get("equipo"),
        usuario_win: params.get("usuario_win"),
      }),
    });
    $("#msg-sol").textContent = "";
    f.reset();
    const caso = { id: d.id, codigo: d.codigo };
    localStorage.setItem("caso", JSON.stringify(caso));
    seguirCaso(caso);
  } catch (err) {
    $("#msg-sol").textContent = err.message;
  } finally {
    btn.disabled = false;
  }
});

$("#otra").addEventListener("click", () => {
  clearInterval(timerCaso);
  localStorage.removeItem("caso");
  if (wsChat) wsChat.close();
  wsChat = null;
  $("#chat").hidden = true;
  iniciar();
});

let wsChat = null;

function abrirChat(caso) {
  if (wsChat) return;
  $("#chat").hidden = false;
  $("#form-chat input").disabled = false;
  wsChat = iniciarChat({
    url: `/ws/chat/${caso.id}?codigo=${encodeURIComponent(caso.codigo)}`,
    rolPropio: "solicitante",
    caja: $("#caja-chat"),
    form: $("#form-chat"),
    onResuelta: () => {
  $("#titulo-espera").textContent = "Caso resuelto";
  $("#texto-espera").textContent =
    "El especialista marcó tu solicitud como resuelta. ¡Gracias!";

  setTimeout(() => {
    clearInterval(timerCaso);
    localStorage.removeItem("caso");

    if (wsChat) {
      wsChat.close();
      wsChat = null;
    }

    $("#chat").hidden = true;
    $("#bloque-espera").hidden = true;
    $("#bloque-form").hidden = false;

    cargarListas();
  }, 3000);
},
  });
}

iniciar();