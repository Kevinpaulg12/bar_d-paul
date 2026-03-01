let carrito = [];
let totalVenta = 0;

// 1. Agregar producto (Ahora recibe el STOCK como cuarto parámetro)
function agregarProducto(id, nombre, precio, stock) {
    let productoExistente = carrito.find(item => item.id === id);

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
                cantidad: 1
            });
        } else {
            alert("Este producto se encuentra agotado.");
        }
    }
    actualizarInterfaz();
}

// 2. Controladores de Botones [-] y [+]
function modificarCantidad(id, cambio) {
    let item = carrito.find(item => item.id === id);
    if (item) {
        let nuevaCantidad = item.cantidad + cambio;
        
        if (nuevaCantidad > item.stock) {
            alert(`Stock máximo alcanzado. Solo hay ${item.stock} unidades disponibles.`);
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
    let item = carrito.find(item => item.id === id);
    if (item) {
        let nuevaCantidad = parseInt(valor);
        
        // Si borran el número o ponen letras/negativos, se restaura a 1
        if (isNaN(nuevaCantidad) || nuevaCantidad <= 0) {
            item.cantidad = 1; 
        } 
        // Si intentan escribir "50" y solo hay "12"
        else if (nuevaCantidad > item.stock) {
            alert(`Stock máximo alcanzado. Solo hay ${item.stock} unidades disponibles.`);
            item.cantidad = item.stock; // Lo forza al máximo permitido
        } 
        else {
            item.cantidad = nuevaCantidad;
        }
        actualizarInterfaz();
    }
}

// 4. Eliminar producto
function eliminarProducto(id) {
    carrito = carrito.filter(item => item.id !== id);
    actualizarInterfaz();
}

// 5. Renderizar Interfaz
function actualizarInterfaz() {
    const contenedor = document.getElementById('ticket-items');
    const totalElement = document.getElementById('ticket-total');
    
    contenedor.innerHTML = ''; 
    totalVenta = 0;

    if (carrito.length === 0) {
        contenedor.innerHTML = '<p class="text-gray-500 italic text-sm text-center mt-10">No hay productos seleccionados...</p>';
        totalElement.innerText = '$0.00';
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

    totalElement.innerText = '$' + totalVenta.toFixed(2);
}
// static/js/sales.js

// --- 1. LÓGICA DE FILTRADO (Manejo de 100+ productos) ---

function filtrarProductos() {
    const busqueda = document.getElementById('buscador').value.toLowerCase();
    const cards = document.querySelectorAll('.producto-card');

    cards.forEach(card => {
        const nombre = card.getAttribute('data-nombre');
        const codigo = card.getAttribute('data-codigo');
        const categoria = card.getAttribute('data-categoria');

        // Busca en nombre, código o categoría
        if (nombre.includes(busqueda) || codigo.includes(busqueda) || categoria.includes(busqueda)) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}

function filtrarCategoria(slug) {
    const cards = document.querySelectorAll('.producto-card');
    const botones = document.querySelectorAll('.cat-btn');
    const busquedaInput = document.getElementById('buscador');

    // 1. Limpiar búsqueda si se filtra por categoría
    busquedaInput.value = '';

    // 2. Actualizar contador
    let count = 0;

    // 3. Cambiar estado visual de los botones
    botones.forEach(btn => {
        btn.classList.remove('bg-brand-500', 'text-white', 'active', 'shadow-brand-500/30');
        btn.classList.add('bg-dark-900', 'text-gray-400', 'border', 'border-dark-600');
    });

    // Como event.currentTarget no es fiable si la función no es llamada por un evento,
    // buscamos el botón correcto por su atributo onclick.
    const activeButton = document.querySelector(`.cat-btn[onclick="filtrarCategoria('${slug}')"]`);
    if (activeButton) {
        activeButton.classList.add('bg-brand-500', 'text-white', 'active', 'shadow-brand-500/30');
        activeButton.classList.remove('bg-dark-900', 'text-gray-400', 'border', 'border-dark-600');
    }


    // 4. Filtrar las tarjetas
    cards.forEach(card => {
        const cat = card.getAttribute('data-categoria');
        if (slug === 'todas' || cat === slug) {
            card.style.display = 'block';
            count++;
        } else {
            card.style.display = 'none';
        }
    });

    document.getElementById('productos-count').innerText = count;
}

function limpiarFiltros() {
    // 1. Limpiar el campo de búsqueda
    document.getElementById('buscador').value = '';
    
    // 2. Simular clic en "Todas" para resetear la categoría y la UI
    const botonTodas = document.querySelector('.cat-btn[onclick="filtrarCategoria(\'todas\')"]');
    if (botonTodas) {
        botonTodas.click();
    }
}

// --- ORDENAR POR DEMANDA O CATEGORÍA ---

let vistaActual = 'demanda'; // Por defecto mostramos por demanda

function ordenarPorDemanda() {
    vistaActual = 'demanda';
    
    // Actualizar botones
    document.getElementById('btn-demanda').classList.add('bg-brand-500', 'text-white', 'shadow-lg', 'shadow-brand-500/30');
    document.getElementById('btn-demanda').classList.remove('bg-dark-800', 'text-gray-400');
    document.getElementById('btn-categoria').classList.remove('bg-brand-500', 'text-white', 'shadow-lg', 'shadow-brand-500/30');
    document.getElementById('btn-categoria').classList.add('bg-dark-800', 'text-gray-400');
    
    // Mostrar todas las categorías y ordenar por demanda
    filtrarCategoria('todas');
    
    // Reordenar productos por data-demand (cantidad vendida)
    const catalogo = document.getElementById('catalogo');
    const productos = Array.from(catalogo.querySelectorAll('.producto-card'));
    
    productos.sort((a, b) => {
        const demandaA = parseInt(a.getAttribute('data-demanda') || '0');
        const demandaB = parseInt(b.getAttribute('data-demanda') || '0');
        return demandaB - demandaA; // Descendente (más vendidos primero)
    });
    
    // Redibujar en orden
    productos.forEach(prod => catalogo.appendChild(prod));
}

function ordenarPorCategoria() {
    vistaActual = 'categoria';
    
    // Actualizar botones
    document.getElementById('btn-categoria').classList.add('bg-brand-500', 'text-white', 'shadow-lg', 'shadow-brand-500/30');
    document.getElementById('btn-categoria').classList.remove('bg-dark-800', 'text-gray-400');
    document.getElementById('btn-demanda').classList.remove('bg-brand-500', 'text-white', 'shadow-lg', 'shadow-brand-500/30');
    document.getElementById('btn-demanda').classList.add('bg-dark-800', 'text-gray-400');
    
    // Reordenar productos por categoría y demanda dentro de cada categoría
    const catalogo = document.getElementById('catalogo');
    const productos = Array.from(catalogo.querySelectorAll('.producto-card'));
    
    productos.sort((a, b) => {
        const catA = a.getAttribute('data-categoria') || '';
        const catB = b.getAttribute('data-categoria') || '';
        
        // Primero ordena por categoría alfabéticamente
        if (catA !== catB) {
            return catA.localeCompare(catB);
        }
        
        // Dentro de la misma categoría, ordena por demanda (descendente)
        const demandaA = parseInt(a.getAttribute('data-demanda') || '0');
        const demandaB = parseInt(b.getAttribute('data-demanda') || '0');
        return demandaB - demandaA;
    });
    
    // Redibujar en orden
    productos.forEach(prod => catalogo.appendChild(prod));
}

// --- 2. LÓGICA DE PAGO DINÁMICO ---

function toggleTransferencia() {
    const metodo = document.getElementById('metodo_pago').value;
    const divTransferencia = document.getElementById('campos_transferencia');
    const paymentSection = document.getElementById('payment-section');

    if (metodo === 'TRANSFERENCIA') {
        divTransferencia.style.display = 'block';
        paymentSection.classList.add('hidden'); // Oculta la sección de efectivo
        divTransferencia.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } else {
        divTransferencia.style.display = 'none';
        // No mostramos la sección de pago aquí, solo manejamos la de transferencia
    }
}

// --- 3. LÓGICA DE PAGO ---

function procesarPago() {
    if (carrito.length === 0) {
        alert("⚠️ El ticket está vacío. Agrega productos antes de pagar.");
        return;
    }

    const metodo = document.getElementById('metodo_pago').value;

    if (metodo === 'TRANSFERENCIA') {
        // Si es transferencia, se finaliza la venta directamente
        finalizarVenta();
    } else {
        // Si es efectivo, muestra la sección para calcular el cambio
        const paymentSection = document.getElementById('payment-section');
        const isHidden = paymentSection.classList.contains('hidden');
        
        if (isHidden) {
            document.getElementById('efectivo').value = '';
            document.getElementById('cambio').innerText = '$0.00';
            paymentSection.classList.remove('hidden');
            document.getElementById('efectivo').focus();
        } else {
            // Si ya está visible, el segundo clic en "Confirmar" finaliza la venta
            finalizarVenta();
        }
    }
}
function togglePaymentSection() {
    const paymentSection = document.getElementById('payment-section');
    paymentSection.classList.add('hidden');
}

function calcularCambio() {
    const efectivoInput = document.getElementById('efectivo');
    const cambioElement = document.getElementById('cambio');
    
    let efectivo = parseFloat(efectivoInput.value) || 0;
    let cambio = efectivo - totalVenta;

    if (cambio < 0) {
        cambio = 0;
    }

    cambioElement.innerText = '$' + cambio.toFixed(2);
}

// --- 4. PROCESO DE FINALIZAR VENTA ---
async function finalizarVenta() {
    if (carrito.length === 0) {
        alert("⚠️ El ticket está vacío.");
        return;
    }

    const clienteInput = document.getElementById('cliente_nombre');
    const metodoInput = document.getElementById('metodo_pago');
    const bancoInput = document.getElementById('banco');
    const codigoInput = document.getElementById('codigo_ref');
    const efectivo = parseFloat(document.getElementById('efectivo').value) || 0;

    // Validación de transferencia
    if (metodoInput.value === 'TRANSFERENCIA' && (!bancoInput.value || !codigoInput.value)) {
        alert("❌ Por favor, ingrese el banco y el código de comprobante.");
        return;
    }

    // Validación de efectivo si el método es EFECTIVO
    if (metodoInput.value === 'EFECTIVO' && efectivo < totalVenta) {
        alert("❌ El efectivo recibido es menor al total de la venta.");
        return;
    }
    
    // Ocultar sección de pago antes de procesar
    togglePaymentSection();

    try {
        const response = await fetch('/api/procesar-venta/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                carrito: carrito,
                total: totalVenta,
                cliente: clienteInput.value,
                metodo_pago: metodoInput.value,
                banco: bancoInput.value,
                codigo: codigoInput.value
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            alert("✅ Venta registrada correctamente.");
            
            if (typeof imprimirComprobante === 'function') {
                imprimirComprobante(data.venta_id, clienteInput.value, carrito, totalVenta);
            }
            
            // --- ACTUALIZACIÓN DINÁMICA DE STOCK ---
            data.updated_stock.forEach(prod => {
                const card = document.querySelector(`.producto-card[data-id="${prod.id}"]`);
                if (!card) return;

                if (prod.stock_actual === 0) {
                    card.remove(); // Elimina la tarjeta si el stock es 0
                } else {
                    // Actualiza el texto del stock
                    const stockDisplay = card.querySelector('.stock-display');
                    if (stockDisplay) {
                        stockDisplay.innerText = prod.stock_actual;
                    }

                    // Actualiza el parámetro de stock en la función onclick
                    // ¡Esto es más complejo de lo que parece! La forma más robusta
                    // es reconstruir el atributo o manejar los datos de otra forma.
                    // Por simplicidad, aquí usamos una expresión regular.
                    let onclickAttr = card.getAttribute('onclick');
                    let newOnclickAttr = onclickAttr.replace(/,\s*\d+\)$/, `, ${prod.stock_actual})`);
                    card.setAttribute('onclick', newOnclickAttr);
                }
            });

            // Limpia el carrito y la interfaz sin recargar
            carrito = [];
            actualizarInterfaz();
            
            // Limpiar campos de cliente y pago
            clienteInput.value = 'Consumidor Final';
            metodoInput.value = 'EFECTIVO';
            bancoInput.value = '';
            codigoInput.value = '';
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

    const productoId = document.getElementById('baja_producto_id').value;
    const cantidad = document.getElementById('baja_cantidad').value;
    const motivo = document.getElementById('baja_motivo').value;
    const tipo = document.getElementById('baja_tipo') ? document.getElementById('baja_tipo').value : 'GENERAL';

    if (!productoId || !cantidad || !motivo) {
        alert("⚠️ Por favor completa todos los campos del reporte.");
        return;
    }

    try {
        const response = await fetch('/productos/solicitar-baja/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                producto_id: productoId,
                cantidad: parseInt(cantidad),
                motivo: `[${tipo}] ${motivo}` // Combinamos el tipo con el motivo
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            alert("📩 Reporte enviado con éxito. El administrador revisará la solicitud.");
            cerrarModalBaja();
            // Limpiar campos
            document.getElementById('baja_cantidad').value = '';
            document.getElementById('baja_motivo').value = '';
        } else {
            console.error("Error del servidor:", data);
            alert("❌ Error: " + (data.error || "No se pudo enviar el reporte"));
        }
    } catch (error) {
        console.error("Error de red:", error);
        alert("💥 Error de conexión. Verifica que la ruta /productos/solicitar-baja/ exista.");
    }
}
// --- UTILIDADES ---

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}