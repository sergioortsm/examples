# confirmacion.py

import sys

def mostrar_resumen_y_confirmar(horario, modo_interactivo, logger, obtener_hora_variada, construir_body):
    print("📋 Fichajes programados para hoy:\n")
    logger.info("Fichajes programados para hoy:")

    fichajes_previstos = []

    for hora_str, tipo in horario:
        hora_real = obtener_hora_variada(hora_str)
        body = construir_body(hora_real)
        linea = f" - {tipo.upper()} → {hora_real} ({body['clockDateTime']})"
        print(linea)
        logger.info(linea)
        fichajes_previstos.append((hora_real, tipo, body))

    if modo_interactivo:
        print("\n¿Deseas continuar con estos fichajes? (s/N): ", end="")
        respuesta = input().strip().lower()
        if respuesta != 's':
            mensaje = "⛔ Fichaje cancelado por el usuario desde consola."
            print("\n" + mensaje)
            logger.info(mensaje)
            sys.exit(0)
        else:
            logger.info("✅ Usuario confirmó continuar con los fichajes.")
    else:
        logger.info("🤖 Modo automático: fichaje ejecutado sin confirmación.")

    return fichajes_previstos
