let carrito = [];
let totalVenta = 0;

function puedeVender() {
  // Default: true para no romper pantallas antiguas.
  if (typeof window.PUEDE_VENDER === "undefined") return true;
  return !!window.PUEDE_VENDER;
}

function requirePuedeVender() {
  if (puedeVender()) return true;
  alert(
    "Acceso bloqueado: solo el Vendedor Responsable puede añadir productos y confirmar ventas.",
  );
  return false;
}

document.addEventListener("DOMContentLoaded", () => {
  setupClienteUI();
  setupBancoUI();
  setupPosTicketUI();
});

function setupPosTicketUI() {
  setupPosTicketCollapse();
  setupCheckoutDetailsCollapse();
  setupQuickCheckout();
}

function setupQuickCheckout() {
  const quickBtn = document.getElementById("quick-checkout");
  if (!quickBtn) return;

  quickBtn.addEventListener("click", () => {
    const ticket = document.getElementById("pos-ticket");
    const toggleTicket = document.getElementById("toggle-ticket");
    if (ticket?.classList.contains("is-collapsed")) toggleTicket?.click();

    const details = document.getElementById("checkout-details");
    const toggleDetails = document.getElementById("toggle-checkout-details");
    if (details && details.classList.contains("hidden")) toggleDetails?.click();

    setTimeout(() => {
      document.getElementById("metodo_pago")?.focus();
    }, 80);
  });
}

function setupPosTicketCollapse() {
  const ticket = document.getElementById("pos-ticket");
  const btn = document.getElementById("toggle-ticket");
  const body = document.getElementById("ticket-body");
  const expandedText = btn?.querySelector("[data-ticket-expanded]");
  const collapsedText = btn?.querySelector("[data-ticket-collapsed]");

  if (!ticket || !btn || !body) return;

  const STORAGE_KEY = "pos_ticket_collapsed";
  const mq = window.matchMedia("(min-width: 1024px)"); // lg

  function setCollapsed(collapsed) {
    // En desktop siempre expandido.
    if (mq.matches) collapsed = false;

    ticket.classList.toggle("is-collapsed", !!collapsed);
    btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    expandedText?.classList.toggle("hidden", !!collapsed);
    collapsedText?.classList.toggle("hidden", !collapsed);
  }

  function loadInitialState() {
    if (mq.matches) return setCollapsed(false);
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === null) return setCollapsed(true); // default: minimizar en móvil
    return setCollapsed(stored === "1");
  }

  btn.addEventListener("click", () => {
    const collapsed = !ticket.classList.contains("is-collapsed");
    setCollapsed(collapsed);
    if (!mq.matches) localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
  });

  if (mq.addEventListener) mq.addEventListener("change", loadInitialState);
  else if (mq.addListener) mq.addListener(loadInitialState);

  loadInitialState();
}

function setupCheckoutDetailsCollapse() {
  const btn = document.getElementById("toggle-checkout-details");
  const details = document.getElementById("checkout-details");
  const icon = btn?.querySelector("[data-checkout-icon]");

  if (!btn || !details) return;

  function setOpen(open) {
    details.classList.toggle("hidden", !open);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    icon?.classList.toggle("rotate-180", open);
  }

  // En móvil iniciamos cerrado; en desktop lo maneja `lg:block`.
  setOpen(false);

  btn.addEventListener("click", () => {
    const open = details.classList.contains("hidden");
    setOpen(open);
    if (open) {
      setTimeout(() => {
        const first = details.querySelector("select, input, textarea, button");
        first?.focus?.();
      }, 50);
    }
  });
}

function setupClienteUI() {
  const clienteTipo = document.getElementById("cliente_tipo");
  const clienteBox = document.getElementById("cliente_personalizado");
  const clienteInput = document.getElementById("cliente_nombre"); // hidden
  const clienteNombrePila = document.getElementById("cliente_nombre_pila");
  const clienteApellido = document.getElementById("cliente_apellido");
  const metodoInput = document.getElementById("metodo_pago");
  const hint = document.getElementById("cliente-hint");

  if (!clienteTipo || !clienteBox || !clienteInput) return;

  function syncCliente() {
    const tipo = clienteTipo.value;
    const metodo = metodoInput ? metodoInput.value : "EFECTIVO";

    // Crédito fuerza personalizado
    if (metodo === "CREDITO" && tipo !== "PERSONALIZADO") {
      clienteTipo.value = "PERSONALIZADO";
    }

    const effectiveTipo = clienteTipo.value;

    if (effectiveTipo === "PERSONALIZADO") {
      clienteBox.classList.remove("hidden");
      const n = (clienteNombrePila?.value || "").trim();
      const a = (clienteApellido?.value || "").trim();
      clienteInput.value = `${n} ${a}`.trim();
      if (hint) hint.textContent = metodo === "CREDITO" ? "Obligatorio en crédito" : "";
    } else {
      clienteBox.classList.add("hidden");
      clienteInput.value = "Consumidor Final";
      if (hint) hint.textContent = "";
    }
  }

  clienteTipo.addEventListener("change", syncCliente);
  clienteNombrePila?.addEventListener("input", syncCliente);
  clienteApellido?.addEventListener("input", syncCliente);
  metodoInput?.addEventListener("change", syncCliente);

  syncCliente();
}

function setupBancoUI() {
  const bancoHidden = document.getElementById("banco"); // hidden (backend)
  const bancoSelect = document.getElementById("banco_select");
  const bancoOtroWrap = document.getElementById("banco_otro_wrap");
  const bancoOtro = document.getElementById("banco_otro");

  if (!bancoHidden || !bancoSelect) return;

  function syncBanco() {
    const selected = (bancoSelect.value || "").toUpperCase();

    if (selected === "OTRO") {
      bancoOtroWrap?.classList.remove("hidden");
      const nombre = (bancoOtro?.value || "").trim();
      bancoHidden.value = nombre;
    } else {
      bancoOtroWrap?.classList.add("hidden");
      bancoHidden.value = selected;
    }
  }

  bancoSelect.addEventListener("change", () => {
    syncBanco();
    if (bancoSelect.value === "OTRO") {
      setTimeout(() => bancoOtro?.focus(), 50);
    }
  });
  bancoOtro?.addEventListener("input", syncBanco);

  syncBanco();
}

// 1. Agregar producto (Ahora recibe el STOCK como cuarto parámetro)
function agregarProducto(id, nombre, precio, stock) {
  if (!requirePuedeVender()) return;
  let productoExistente = carrito.find((item) => item.id === id);

  if (productoExistente) {
    // Bloqueo de seguridad: No sumar si ya alcanzó el límite
    if (productoExistente.cantidad < stock) {
      productoExistente.cantidad += 1;
    } else {
      alert(`Stock máximo alcanzado. Solo hay ${stock} unidades de ${nombre}.`);
    }
  } else {
    if (stock > 0) {
      carrito.push({
        id: id,
        nombre: nombre,
        precio: parseFloat(precio),
        stock: parseInt(stock),
        cantidad: 1,
        es_promocion: false
      });
    } else {
      alert("Este producto se encuentra agotado.");
    }
  }
  actualizarInterfaz();
}

// 1.1 Agregar promoción al carrito
function agregarPromocion(id, nombre, precio) {
  if (!requirePuedeVender()) return;
  
  // Usar ID negativo para promociones para diferenciarlas de productos normales
  let promoId = -id;
  let productoExistente = carrito.find((item) => item.id === promoId);

  if (productoExistente) {
    productoExistente.cantidad += 1;
  } else {
    // Las promociones no tienen límite de stock (se valida al procesar la venta)
    carrito.push({
      id: promoId,
      nombre: nombre,
      precio: parseFloat(precio),
      stock: 999, // Stock alto para permitir agregar
      cantidad: 1,
      es_promocion: true,
      promocion_id: id
    });
  }
  actualizarInterfaz();
}

// 2. Controladores de Botones [-] y [+]
function modificarCantidad(id, cambio) {
  if (!requirePuedeVender()) return;
  let item = carrito.find((item) => item.id === id);
  if (item) {
    let nuevaCantidad = item.cantidad + cambio;

    if (nuevaCantidad > item.stock) {
      alert(
        `Stock máximo alcanzado. Solo hay ${item.stock} unidades disponibles.`,
      );
      return;
    }

    if (nuevaCantidad > 0) {
      item.cantidad = nuevaCantidad;
    } else {
      // Si resta por debajo de 1, elimina el producto del ticket
      eliminarProducto(id);
      return;
    }
    actualizarInterfaz();
  }
}

// 3. Controlador de ingreso manual (Escribir directo el número)
function ingresarCantidadManual(id, valor) {
  if (!requirePuedeVender()) return;
  let item = carrito.find((item) => item.id === id);
  if (item) {
    let nuevaCantidad = parseInt(valor);

    // Si borran el número o ponen letras/negativos, se restaura a 1
    if (isNaN(nuevaCantidad) || nuevaCantidad <= 0) {
      item.cantidad = 1;
    }
    // Si intentan escribir "50" y solo hay "12"
    else if (nuevaCantidad > item.stock) {
      alert(
        `Stock máximo alcanzado. Solo hay ${item.stock} unidades disponibles.`,
      );
      item.cantidad = item.stock; // Lo forza al máximo permitido
    } else {
      item.cantidad = nuevaCantidad;
    }
    actualizarInterfaz();
  }
}

// 4. Eliminar producto
function eliminarProducto(id) {
  if (!requirePuedeVender()) return;
  carrito = carrito.filter((item) => item.id !== id);
  actualizarInterfaz();
}

// 5. Renderizar Interfaz
function actualizarInterfaz() {
  const contenedor = document.getElementById("ticket-items");
  const totalElement = document.getElementById("ticket-total");
  const totalMini = document.getElementById("ticket-total-mini");
  const countMini = document.getElementById("ticket-count-mini");

  contenedor.innerHTML = "";
  totalVenta = 0;
  const itemsCount = carrito.reduce((acc, item) => acc + (item.cantidad || 0), 0);

  if (carrito.length === 0) {
    contenedor.innerHTML =
      '<p class="text-gray-500 italic text-sm text-center mt-10">No hay productos seleccionados...</p>';
    totalElement.innerText = "$0.00";
    if (totalMini) totalMini.innerText = "$0.00";
    if (countMini) countMini.innerText = "0";
    return;
  }

  carrito.forEach((item) => {
    let subtotal = item.precio * item.cantidad;
    totalVenta += subtotal;

    // Se dibuja cada producto con su control - 1 +
    contenedor.innerHTML += `
            <div class="bg-dark-900 p-3 rounded-xl border border-dark-700 mb-2">
                <div class="flex justify-between items-start mb-2">
                    <span class="font-bold text-sm text-white truncate w-40">${item.nombre}</span>
                    <span class="font-bold text-brand-400">$${subtotal.toFixed(2)}</span>
                </div>
                
                <div class="flex justify-between items-center">
                    <div class="flex items-center bg-dark-800 rounded-lg p-1">
                        <button onclick="modificarCantidad(${item.id}, -1)" class="w-7 h-7 flex items-center justify-center text-gray-400 hover:text-white hover:bg-red-500/20 rounded-md transition">-</button>
                        <input type="text" readonly value="${item.cantidad}" class="w-8 text-center bg-transparent text-white text-xs font-bold border-none focus:ring-0">
                        <button onclick="modificarCantidad(${item.id}, 1)" class="w-7 h-7 flex items-center justify-center text-gray-400 hover:text-white hover:bg-brand-500/20 rounded-md transition">+</button>
                    </div>
                    <button onclick="eliminarProducto(${item.id})" class="text-gray-600 hover:text-red-500 transition">
                        <i class="fa-solid fa-trash-can text-xs"></i>
                    </button>
                </div>
            </div>
        `;
  });

  totalElement.innerText = "$" + totalVenta.toFixed(2);
  if (totalMini) totalMini.innerText = "$" + totalVenta.toFixed(2);
  if (countMini) countMini.innerText = String(itemsCount);
}
// static/js/sales.js

// --- 1. LÓGICA DE FILTRADO (Manejo de 100+ productos) ---

function filtrarProductos() {
  const busqueda = document.getElementById("buscador").value.toLowerCase();
  const cards = document.querySelectorAll(".producto-card");

  cards.forEach((card) => {
    const nombre = card.getAttribute("data-nombre");
    const codigo = card.getAttribute("data-codigo");
    const categoria = card.getAttribute("data-categoria");

    // Busca en nombre, código o categoría
    if (
      nombre.includes(busqueda) ||
      codigo.includes(busqueda) ||
      categoria.includes(busqueda)
    ) {
      card.style.display = "block";
    } else {
      card.style.display = "none";
    }
  });
}

function filtrarCategoria(slug) {
  const cards = document.querySelectorAll(".producto-card");
  const botones = document.querySelectorAll(".cat-btn");
  const busquedaInput = document.getElementById("buscador");

  // 1. Limpiar búsqueda si se filtra por categoría
  busquedaInput.value = "";

  // 2. Actualizar contador
  let count = 0;

  // 3. Cambiar estado visual de los botones
  botones.forEach((btn) => {
    btn.classList.remove(
      "bg-brand-500",
      "text-white",
      "active",
      "shadow-brand-500/30",
    );
    btn.classList.add(
      "bg-dark-900",
      "text-gray-400",
      "border",
      "border-dark-600",
    );
  });

  // Como event.currentTarget no es fiable si la función no es llamada por un evento,
  // buscamos el botón correcto por su atributo onclick.
  const activeButton = document.querySelector(
    `.cat-btn[onclick="filtrarCategoria('${slug}')"]`,
  );
  if (activeButton) {
    activeButton.classList.add(
      "bg-brand-500",
      "text-white",
      "active",
      "shadow-brand-500/30",
    );
    activeButton.classList.remove(
      "bg-dark-900",
      "text-gray-400",
      "border",
      "border-dark-600",
    );
  }

  // 4. Filtrar las tarjetas
  cards.forEach((card) => {
    const cat = card.getAttribute("data-categoria");
    if (slug === "todas" || cat === slug) {
      card.style.display = "block";
      count++;
    } else {
      card.style.display = "none";
    }
  });

  document.getElementById("productos-count").innerText = count;
}

function limpiarFiltros() {
  // 1. Limpiar el campo de búsqueda
  document.getElementById("buscador").value = "";

  // 2. Simular clic en "Todas" para resetear la categoría y la UI
  const botonTodas = document.querySelector(
    ".cat-btn[onclick=\"filtrarCategoria('todas')\"]",
  );
  if (botonTodas) {
    botonTodas.click();
  }
}

// --- ORDENAR POR DEMANDA O CATEGORÍA ---

let vistaActual = "demanda"; // Por defecto mostramos por demanda

function ordenarPorDemanda() {
  vistaActual = "demanda";

  // Actualizar botones
  document
    .getElementById("btn-demanda")
    .classList.add(
      "bg-brand-500",
      "text-white",
      "shadow-lg",
      "shadow-brand-500/30",
    );
  document
    .getElementById("btn-demanda")
    .classList.remove("bg-dark-800", "text-gray-400");
  document
    .getElementById("btn-categoria")
    .classList.remove(
      "bg-brand-500",
      "text-white",
      "shadow-lg",
      "shadow-brand-500/30",
    );
  document
    .getElementById("btn-categoria")
    .classList.add("bg-dark-800", "text-gray-400");

  // Mostrar todas las categorías y ordenar por demanda
  filtrarCategoria("todas");

  // Reordenar productos por data-demand (cantidad vendida)
  const catalogo = document.getElementById("catalogo");
  const productos = Array.from(catalogo.querySelectorAll(".producto-card"));

  productos.sort((a, b) => {
    const demandaA = parseInt(a.getAttribute("data-demanda") || "0");
    const demandaB = parseInt(b.getAttribute("data-demanda") || "0");
    return demandaB - demandaA; // Descendente (más vendidos primero)
  });

  // Redibujar en orden
  productos.forEach((prod) => catalogo.appendChild(prod));
}

function ordenarPorCategoria() {
  vistaActual = "categoria";

  // Actualizar botones
  document
    .getElementById("btn-categoria")
    .classList.add(
      "bg-brand-500",
      "text-white",
      "shadow-lg",
      "shadow-brand-500/30",
    );
  document
    .getElementById("btn-categoria")
    .classList.remove("bg-dark-800", "text-gray-400");
  document
    .getElementById("btn-demanda")
    .classList.remove(
      "bg-brand-500",
      "text-white",
      "shadow-lg",
      "shadow-brand-500/30",
    );
  document
    .getElementById("btn-demanda")
    .classList.add("bg-dark-800", "text-gray-400");

  // Reordenar productos por categoría y demanda dentro de cada categoría
  const catalogo = document.getElementById("catalogo");
  const productos = Array.from(catalogo.querySelectorAll(".producto-card"));

  productos.sort((a, b) => {
    const catA = a.getAttribute("data-categoria") || "";
    const catB = b.getAttribute("data-categoria") || "";

    // Primero ordena por categoría alfabéticamente
    if (catA !== catB) {
      return catA.localeCompare(catB);
    }

    // Dentro de la misma categoría, ordena por demanda (descendente)
    const demandaA = parseInt(a.getAttribute("data-demanda") || "0");
    const demandaB = parseInt(b.getAttribute("data-demanda") || "0");
    return demandaB - demandaA;
  });

  // Redibujar en orden
  productos.forEach((prod) => catalogo.appendChild(prod));
}

// --- 2. LÓGICA DE PAGO DINÁMICO ---

function toggleTransferencia() {
  const metodo = document.getElementById("metodo_pago").value;
  const divTransferencia = document.getElementById("campos_transferencia");
  const paymentSection = document.getElementById("payment-section");
  const divCredito = document.getElementById("campos_credito");
  const codigoInput = document.getElementById("codigo_ref");
  const nombreInput = document.getElementById("cliente_nombre_pila");

  if (metodo === "TRANSFERENCIA") {
    divTransferencia.style.display = "block";
    if (divCredito) divCredito.classList.add("hidden");
    paymentSection.classList.add("hidden"); // Oculta la sección de efectivo
    divTransferencia.scrollIntoView({ behavior: "smooth", block: "nearest" });
    // Foco para agilizar
    setTimeout(() => codigoInput?.focus(), 50);
  } else if (metodo === "CREDITO") {
    divTransferencia.style.display = "none";
    if (divCredito) divCredito.classList.remove("hidden");
    paymentSection.classList.add("hidden");
    setTimeout(() => nombreInput?.focus(), 50);
  } else {
    divTransferencia.style.display = "none";
    if (divCredito) divCredito.classList.add("hidden");
    // No mostramos la sección de pago aquí, solo manejamos la de transferencia
  }
}

// --- 3. LÓGICA DE PAGO ---

function procesarPago() {
  if (!requirePuedeVender()) return;
  if (carrito.length === 0) {
    alert("⚠️ El ticket está vacío. Agrega productos antes de pagar.");
    return;
  }

  const metodo = document.getElementById("metodo_pago").value;

  if (metodo === "TRANSFERENCIA" || metodo === "CREDITO") {
    // Si es transferencia o crédito, se finaliza la venta directamente
    finalizarVenta();
  } else {
    // Si es efectivo, muestra la sección para calcular el cambio
    const paymentSection = document.getElementById("payment-section");
    const isHidden = paymentSection.classList.contains("hidden");

    if (isHidden) {
      document.getElementById("efectivo").value = "";
      document.getElementById("cambio").innerText = "$0.00";
      paymentSection.classList.remove("hidden");
      paymentSection.scrollIntoView({ behavior: "smooth", block: "nearest" });
      document.getElementById("efectivo").focus();
    } else {
      // Si ya está visible, el segundo clic en "Confirmar" finaliza la venta
      finalizarVenta();
    }
  }
}
function togglePaymentSection() {
  const paymentSection = document.getElementById("payment-section");
  paymentSection.classList.add("hidden");
}

function calcularCambio() {
  const efectivoInput = document.getElementById("efectivo");
  const cambioElement = document.getElementById("cambio");

  let efectivo = parseFloat(efectivoInput.value) || 0;
  let cambio = efectivo - totalVenta;

  if (cambio < 0) {
    cambio = 0;
  }

  cambioElement.innerText = "$" + cambio.toFixed(2);
}

// --- 4. PROCESO DE FINALIZAR VENTA ---
async function finalizarVenta() {
  if (!requirePuedeVender()) return;
  if (carrito.length === 0) {
    alert("⚠️ El ticket está vacío.");
    return;
  }

  const clienteInput = document.getElementById("cliente_nombre");
  const clienteTipo = document.getElementById("cliente_tipo");
  const clienteNombrePila = document.getElementById("cliente_nombre_pila");
  const clienteApellido = document.getElementById("cliente_apellido");
  const metodoInput = document.getElementById("metodo_pago");
  const bancoInput = document.getElementById("banco"); // hidden (sincronizado por combo)
  const codigoInput = document.getElementById("codigo_ref");
  const efectivo = parseFloat(document.getElementById("efectivo").value) || 0;

  // Construir cliente desde el combo (si existe)
  let clienteFinal = clienteInput ? clienteInput.value : "Consumidor Final";
  if (clienteTipo && clienteTipo.value === "PERSONALIZADO") {
    const n = (clienteNombrePila?.value || "").trim();
    const a = (clienteApellido?.value || "").trim();
    if (!n || !a) {
      alert("❌ Ingresa nombre y apellido del cliente.");
      return;
    }
    clienteFinal = `${n} ${a}`.trim();
  }

  if (metodoInput.value === "CREDITO") {
    // Crédito siempre exige nombre y apellido
    if (!clienteTipo || clienteTipo.value !== "PERSONALIZADO") {
      alert("❌ En crédito debes seleccionar 'Nombre y apellido'.");
      return;
    }
  }

  // Validación de transferencia
  if (
    metodoInput.value === "TRANSFERENCIA" &&
    (!bancoInput.value || !codigoInput.value)
  ) {
    alert("❌ Por favor, ingrese el banco y el código de comprobante.");
    return;
  }

  // Validación de efectivo si el método es EFECTIVO
  if (metodoInput.value === "EFECTIVO" && efectivo < totalVenta) {
    alert("❌ El efectivo recibido es menor al total de la venta.");
    return;
  }

  // Ocultar sección de pago antes de procesar
  togglePaymentSection();

  try {
    const response = await fetch("/api/procesar-venta/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({
        carrito: carrito,
        total: totalVenta,
        cliente: clienteFinal,
        metodo_pago: metodoInput.value,
        banco: bancoInput.value,
        codigo: codigoInput.value,
      }),
    });

    const data = await response.json();

    if (response.ok && data.success) {
      alert("✅ Venta registrada correctamente.");

      if (typeof imprimirComprobante === "function") {
        imprimirComprobante(
          data.venta_id,
          clienteInput.value,
          carrito,
          totalVenta,
        );
      }

      // --- ACTUALIZACIÓN DINÁMICA DE STOCK ---
      data.updated_stock.forEach((prod) => {
        const card = document.querySelector(
          `.producto-card[data-id="${prod.id}"]`,
        );
        if (!card) return;

        if (prod.stock_actual === 0) {
          card.remove(); // Elimina la tarjeta si el stock es 0
        } else {
          // Actualiza el texto del stock
          const stockDisplay = card.querySelector(".stock-display");
          if (stockDisplay) {
            stockDisplay.innerText = prod.stock_actual;
          }

          // Actualiza el parámetro de stock en la función onclick
          // ¡Esto es más complejo de lo que parece! La forma más robusta
          // es reconstruir el atributo o manejar los datos de otra forma.
          // Por simplicidad, aquí usamos una expresión regular.
          let onclickAttr = card.getAttribute("onclick");
          let newOnclickAttr = onclickAttr.replace(
            /,\s*\d+\)$/,
            `, ${prod.stock_actual})`,
          );
          card.setAttribute("onclick", newOnclickAttr);
        }
      });

      // Limpia el carrito y la interfaz sin recargar
      carrito = [];
      actualizarInterfaz();

      // Limpiar campos de cliente y pago
      if (clienteInput) clienteInput.value = "Consumidor Final";
      if (clienteTipo) clienteTipo.value = "CONSUMIDOR_FINAL";
      if (clienteNombrePila) clienteNombrePila.value = "";
      if (clienteApellido) clienteApellido.value = "";
      metodoInput.value = "EFECTIVO";
      bancoInput.value = "";
      codigoInput.value = "";
      toggleTransferencia(); // Oculta campos de transferencia si estaban visibles
    } else {
      alert("❌ Error: " + (data.error || "No se pudo procesar la venta"));
    }
  } catch (error) {
    console.error("Error crítico:", error);
    alert("💥 Error de conexión con el servidor.");
  }
}
// --- FUNCIÓN DE BAJA MEJORADA ---
async function enviarSolicitudBaja() {
  console.log("Intentando enviar reporte de baja...");

  const productoId = document.getElementById("baja_producto_id").value;
  const cantidad = document.getElementById("baja_cantidad").value;
  const motivo = document.getElementById("baja_motivo").value;
  const tipo = document.getElementById("baja_tipo")
    ? document.getElementById("baja_tipo").value
    : "GENERAL";

  if (!productoId || !cantidad || !motivo) {
    alert("⚠️ Por favor completa todos los campos del reporte.");
    return;
  }

  try {
    const response = await fetch("/productos/solicitar-baja/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({
        producto_id: productoId,
        cantidad: parseInt(cantidad),
        motivo: `[${tipo}] ${motivo}`, // Combinamos el tipo con el motivo
      }),
    });

    const data = await response.json();

    if (response.ok && data.success) {
      alert(
        "📩 Reporte enviado con éxito. El administrador revisará la solicitud.",
      );
      cerrarModalBaja();
      // Limpiar campos
      document.getElementById("baja_cantidad").value = "";
      document.getElementById("baja_motivo").value = "";
    } else {
      console.error("Error del servidor:", data);
      alert("❌ Error: " + (data.error || "No se pudo enviar el reporte"));
    }
  } catch (error) {
    console.error("Error de red:", error);
    alert(
      "💥 Error de conexión. Verifica que la ruta /productos/solicitar-baja/ exista.",
    );
  }
}
// --- UTILIDADES ---

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";");
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === name + "=") {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}
