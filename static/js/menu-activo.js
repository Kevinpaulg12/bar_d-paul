/**
 * Gestor de Menú Activo Dinámico
 * 
 * Este script gestiona el resaltado automático del elemento del menú
 * basado en la ruta actual de la página.
 * 
 * Características:
 * - Detecta automáticamente la página actual
 * - Aplica estilos activos al botón correspondiente
 * - Maneja menús desplegables ( dropdowns)
 * - Funciona en dispositivos móviles y desktop
 */

document.addEventListener('DOMContentLoaded', function() {
    activarMenuActivo();
});

/**
 * Activa el elemento del menú correspondiente a la URL actual
 */
function activarMenuActivo() {
    // Obtener la ruta actual (sin protocolo ni dominio)
    const rutaActual = window.location.pathname;
    
    // Mapeo de rutas a IDs de menú
    const mapeoRutas = {
        '/': 'menu-dashboard',
        '/dashboard/': 'menu-dashboard',
        '/dashboard/admin/': 'menu-dashboard',
        '/dashboard/vendedor/': 'menu-dashboard',
        '/sales/': 'menu-ventas-dia',
        '/sales/nueva/': 'menu-nueva-venta',
        '/sales/cierre/': 'menu-cierre-caja',
        '/sales/reportes/': 'menu-mis-reportes',
        '/sales/gastos/': 'menu-gastos',
        '/productos/': 'menu-entrada-stock',
        '/productos/bajas/': 'menu-bajas-pendientes',
        '/productos/bajas/pendientes/': 'menu-bajas-pendientes',
        '/productos/promociones/': 'menu-promociones',
        '/cuentas/usuarios/': 'menu-usuarios',
        '/admin/': 'menu-dashboard',
    };
    
    // Encontrar el elemento del menú que coincida
    let elementoActivo = null;
    
    // Buscar coincidencia exacta primero
    for (const [ruta, id] of Object.entries(mapeoRutas)) {
        if (rutaActual === ruta) {
            elementoActivo = document.getElementById(id);
            break;
        }
    }
    
    // Si no hay coincidencia exacta, buscar por prefijo
    if (!elementoActivo) {
        for (const [ruta, id] of Object.entries(mapeoRutas)) {
            if (rutaActual.startsWith(ruta) && ruta !== '/') {
                elementoActivo = document.getElementById(id);
                break;
            }
        }
    }
    
    // Aplicar estilos activos
    if (elementoActivo) {
        // Remover clase activa de todos los elementos
        document.querySelectorAll('[id^="menu-"]').forEach(el => {
            el.classList.remove('bg-brand-500/10', 'text-brand-500');
            el.classList.add('text-gray-400', 'hover:bg-dark-800', 'hover:text-white');
            
            // Cerrar submenús
            if (el.hasAttribute('data-toggle')) {
                const submenuId = el.getAttribute('data-toggle');
                const submenu = document.getElementById(submenuId);
                if (submenu) {
                    submenu.classList.remove('active');
                }
            }
        });
        
        // Aplicar clase activa al elemento actual
        elementoActivo.classList.forEach(cl => {
            if (cl.includes('hover:')) {
                elementoActivo.classList.remove(cl);
            }
        });
        
        elementoActivo.classList.remove('text-gray-400');
        elementoActivo.classList.add('bg-brand-500/10', 'text-brand-500');
        
        // Si el menú activo tiene un submenu, abrirlo
        if (elementoActivo.hasAttribute('data-toggle')) {
            const submenuId = elementoActivo.getAttribute('data-toggle');
            const submenu = document.getElementById(submenuId);
            if (submenu) {
                submenu.classList.add('active');
            }
        }
    }
}

/**
 * Alterna la visibilidad de un submenú
 * 
 * @param {string} elementId - ID del elemento del menú a togglear
 */
function toggleSubmenu(elementId) {
    const elemento = document.getElementById(elementId);
    if (elemento) {
        elemento.classList.toggle('active');
    }
}

/**
 * Abre un submenú específico
 * 
 * @param {string} elementId - ID del elemento del menú a abrir
 */
function abrirSubmenu(elementId) {
    const elemento = document.getElementById(elementId);
    if (elemento) {
        elemento.classList.add('active');
    }
}

/**
 * Cierra un submenú específico
 * 
 * @param {string} elementId - ID del elemento del menú a cerrar
 */
function cerrarSubmenu(elementId) {
    const elemento = document.getElementById(elementId);
    if (elemento) {
        elemento.classList.remove('active');
    }
}

/**
 * Cierra todos los submenús
 */
function cerrarTodosLosSubmenus() {
    document.querySelectorAll('.dropdown-menu').forEach(menu => {
        menu.classList.remove('active');
    });
}

/**
 * Maneja clics en elementos del menú para cerrar sidebar en móvil
 */
document.querySelectorAll('[id^="menu-"]').forEach(enlace => {
    enlace.addEventListener('click', function() {
        // Cerrar sidebar en móvil
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebar-overlay');
        if (sidebar && !sidebar.classList.contains('-translate-x-full')) {
            sidebar.classList.add('-translate-x-full');
        }
        if (overlay && !overlay.classList.contains('hidden')) {
            overlay.classList.add('hidden');
        }
    });
});

// Activar el menú cuando cambia la ruta (para SPAs)
window.addEventListener('popstate', function() {
    activarMenuActivo();
});
