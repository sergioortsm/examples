# confirmacion.py

def pedirConfirmacionUsuario(MODO_INTERACTIVO, logger):
    if MODO_INTERACTIVO:
        print("\n¿Deseas continuar con estos fichajes? (s/N): ", end="")
        respuesta = input().strip().lower()
        if respuesta != 's':
            mensaje = "⛔ Fichaje cancelado por el usuario desde consola."
            print("\n" + mensaje)
            logger.info(mensaje)
            return False
        else:
            mensaje = "✅ Usuario confirmó continuar con los fichajes."
            print("\n" + mensaje)
            logger.info(mensaje)
            return True
    else:
        logger.info("🤖 Modo automático: fichaje ejecutado sin confirmación.")
        return True

