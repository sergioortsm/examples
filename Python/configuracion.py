from datetime import date

VIGILIAS_NACIONALES = {
    date(2024, 12, 31),  # antes de Año Nuevo
    date(2025, 1, 5),    # antes de Reyes
    date(2025, 3, 19),   # antes de Jueves Santo (coincide con San José)
    date(2025, 3, 20),   # antes de Viernes Santo
    date(2025, 4, 30),   # antes del 1 de mayo
    date(2025, 8, 14),   # antes del 15 de agosto
    date(2025, 12, 5),   # antes del 6 diciembre
    date(2025, 12, 24),  # antes de Navidad
}

FESTIVOS = {
    date(2025, 1, 1),   # Año Nuevo (miércoles)
    date(2025, 1, 6),   # Reyes (lunes)
    date(2025, 3, 20),  # Jueves Santo
    date(2025, 3, 21),  # Viernes Santo
    date(2025, 5, 1),   # Día del Trabajo (jueves)
    date(2025, 8, 15),  # Asunción (viernes)
    date(2025, 10, 12), # Fiesta Nacional (domingo)
    date(2025, 11, 1),  # Todos los Santos (sábado)
    date(2025, 12, 6),  # Día Constitución (sábado)
    date(2025, 12, 8),  # Inmaculada (lunes)
    date(2025, 12, 25), # Navidad (jueves)
}

#Festivos Comunidad de Madrid
FESTIVOS.update({
    date(2025, 3, 19),  # San José (miércoles)
    date(2025, 5, 2),   # Fiesta Comunidad de Madrid (viernes)
    date(2025, 11, 10), # Traslado de La Almudena (lunes)
})

VARIACION_MIN = -8
VARIACION_MAX = 8

HORA_EJECUCION = "08:00"