const $ = (s) => document.querySelector(s);

let token = localStorage.getItem("token_esp");
let nombre = localStorage.getItem("nombre_esp");
let solicitudes = [];
let timer = null;

async function api(ruta, opciones = {}) {
  const r = await fetch(ruta, {
    ...opciones,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: "Bearer " + token } : {})
    },
  });

  const datos = await r.json().catch(() => ({}));

  if (r.status === 401 && token) {
    cerrarSesion();
  }

  if (!r.ok) {
    throw new Error(
      typeof datos.detail === "string"
        ? datos.detail
        : "No se pudo completar la acción"
    );
  }

  return datos;
}

function esc(t) {
  const d = document.createElement("div");
  d.textContent = t ?? "";
  return d.innerHTML;
}

function iniciar() {
  const dentro = Boolean(token);

  document.body.classList.toggle("modo-login", !dentro);

  document.title = dentro ? "esp-panel" : "esp-login";

  const login = $("#vista-login");
  const panel = $("#vista-panel");
  const chat = $("#vista-chat");
  const sesion = $("#sesion");
  const quien = $("#quien");

  if (login) login.hidden = dentro;
  if (panel) panel.hidden = !dentro;
  if (chat) chat.hidden = true;
  if (sesion) sesion.hidden = !dentro;
  if (quien) quien.textContent = nombre || "";

  clearInterval(timer);

  if (dentro) {
    cargarFiltroCategorias();
    cargarPendientes();
    cargarMisCasos();

    timer = setInterval(() => {
      cargarPendientes();
      cargarMisCasos();
    }, 5000);
  }
}

function cerrarSesion() {
  localStorage.removeItem("token_esp");
  localStorage.removeItem("nombre_esp");

  token = null;
  nombre = null;

  solicitudes = [];
  casos = [];

  if (wsChat) {
    wsChat.close();
    wsChat = null;
  }

  iniciar();
}

const formLogin = $("#form-login");

if (formLogin) {
  formLogin.addEventListener("submit", async (e) => {
    e.preventDefault();

    const f = Object.fromEntries(new FormData(e.target));

    try {
      const d = await api("/api/login-especialista", {
        method: "POST",
        body: JSON.stringify({
          usuario: f.usuario,
          password: f.password,
          correo: f.correo
        }),
      });

      token = d.token;
      nombre = d.nombre;

      localStorage.setItem("token_esp", token);
      localStorage.setItem("nombre_esp", nombre);

      e.target.reset();

      const mensaje = $("#msg-esp");
      if (mensaje) mensaje.textContent = "";

      iniciar();

    } catch (err) {
      const mensaje = $("#msg-esp");

      if (mensaje) {
        mensaje.textContent = err.message;
      }
    }
  });
}

const botonSalir = $("#salir");

if (botonSalir) {
  botonSalir.addEventListener("click", cerrarSesion);
}
async function cargarFiltroCategorias() {
  try {
    const cats = await api("/api/categorias");

    const filtro = $("#filtro-categoria");

    if (!filtro) return;

    filtro.innerHTML =
      '<option value="">Todas las categorías</option>' +
      cats
        .map((c) => `<option value="${c.id}">${esc(c.nombre)}</option>`)
        .join("");

  } catch (_) {}
}


function renderizarPendientes() {
  const filtroElemento = $("#filtro-categoria");

  if (!filtroElemento) return;

  const filtro = filtroElemento.value;

  const filas = filtro
    ? solicitudes.filter(
        (s) => s.categoria_id === Number(filtro)
      )
    : solicitudes;

  const contador = $("#contador");
  const vacio = $("#vacio");
  const lista = $("#lista");

  if (contador) {
    contador.textContent = filas.length;
  }

  if (vacio) {
    vacio.hidden = filas.length > 0;

    vacio.textContent =
      solicitudes.length && filtro
        ? "No hay solicitudes pendientes en esta categoría."
        : "No hay solicitudes por atender. Esta lista se actualiza sola.";
  }

  if (!lista) return;

  lista.innerHTML = filas.map((s) => {
    const creada = new Date(
      s.creada_en.endsWith("Z")
        ? s.creada_en
        : `${s.creada_en}Z`
    );

    const hora = creada.toLocaleTimeString("es-CO", {
      hour: "2-digit",
      minute: "2-digit"
    });

    return `
      <article class="caso">

        <h2>${esc(s.categoria)}</h2>

        <div class="meta">
          ${esc(s.solicitante)}
          ·
          ${esc(s.dependencia)}
          ·
          ${hora}
        </div>

        <div class="meta">
          Correo: ${esc(s.correo || "No registrado")}
        </div>

        <p>${esc(s.observacion)}</p>

        <button class="btn" data-id="${s.id}">
          Aceptar asistencia
        </button>

      </article>
    `;
  }).join("");
}

async function cargarPendientes() {
  try {
    solicitudes = await api("/api/solicitudes/pendientes");
    renderizarPendientes();
  } catch (_) {}
}

const filtroCategoria = $("#filtro-categoria");

if (filtroCategoria) {
  filtroCategoria.addEventListener(
    "change",
    renderizarPendientes
  );
}

const lista = $("#lista");

if (lista) {
  lista.addEventListener("click", async (e) => {

    const id = e.target.dataset.id;

    if (!id) return;

    try {

      await api(
        `/api/solicitudes/${id}/aceptar`,
        { method: "POST" }
      );

      await cargarMisCasos();

      abrirCaso(Number(id));

    } catch (err) {
      alert(err.message);
    }

    cargarPendientes();
  });
}

let casos = [];
let wsChat = null;
let casoActual = null;

async function cargarMisCasos() {
  try {

    casos = await api(
      "/api/solicitudes/mis-casos"
    );

    const misCasos = $("#mis-casos");

    if (!misCasos) return;

    misCasos.innerHTML = casos.map((s) => `
      <article class="caso">

        <h2>${esc(s.categoria)}</h2>

        <div class="meta">
          ${esc(s.solicitante)}
          ·
          ${esc(s.dependencia)}
        </div>

        <div class="meta">
          Correo: ${esc(s.correo || "No registrado")}
        </div>

        <p>${esc(s.observacion)}</p>

        <button class="btn" data-abrir="${s.id}">
          Abrir chat
        </button>

      </article>
    `).join("");

  } catch (_) {}
}

function abrirCaso(id) {

  const s = casos.find((c) => c.id === id);

  if (!s) return;

  casoActual = id;

  const panel = $("#vista-panel");
  const chat = $("#vista-chat");
  const titulo = $("#titulo-chat");
  const input = $("#form-chat input");
  const caja = $("#caja-chat");
  const formulario = $("#form-chat");

  if (!panel || !chat) return;

  panel.hidden = true;
  chat.hidden = false;

  if (titulo) {
    titulo.textContent =
      `${s.solicitante} · ${s.categoria}`;
  }

  if (input) {
    input.disabled = false;
  }

  if (wsChat) {
    wsChat.close();
  }

  wsChat = iniciarChat({
    url: `/ws/chat/${id}?token=${encodeURIComponent(token)}`,
    rolPropio: "especialista",
    caja: caja,
    form: formulario,
    onResuelta: volverPanel,
  });
}


function volverPanel() {

  if (wsChat) {
    wsChat.close();
  }

  wsChat = null;

  const chat = $("#vista-chat");
  const panel = $("#vista-panel");

  if (chat) chat.hidden = true;
  if (panel) panel.hidden = false;

  cargarMisCasos();
  cargarPendientes();
}


const volver = $("#volver-panel");

if (volver) {
  volver.addEventListener(
    "click",
    volverPanel
  );
}


const misCasos = $("#mis-casos");

if (misCasos) {

  misCasos.addEventListener("click", (e) => {

    const id = e.target.dataset.abrir;

    if (id) {
      abrirCaso(Number(id));
    }

  });

}

const resolver = $("#resolver");

if (resolver) {

  resolver.addEventListener("click", async () => {

    if (
      !confirm(
        "¿Marcar este caso como resuelto?"
      )
    ) {
      return;
    }

    try {

      await api(
        `/api/solicitudes/${casoActual}/resolver`,
        { method: "POST" }
      );

      volverPanel();

    } catch (err) {
      alert(err.message);
    }

  });

}

iniciar();
