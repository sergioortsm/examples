## Plan: Adaptar configurador para bot v2

Evolucionar el configurador existente de Personio para la nueva versión del bot, manteniéndolo ligero: solo campos mínimos operativos, validación básica de tipos y sin migración automática de configuraciones antiguas. La estrategia es conservar la base actual y ajustar cobertura/UX para evitar romper el flujo de guardado y arranque del servicio.

**Steps**
1. Fase 1 - Cerrar contrato mínimo v2
2. Definir el set exacto de claves mínimas que el configurador debe editar (alineado con el uso real en servicio/login/cliente): employee_id, timezone, base_url, horarios, headless, modo_prueba, modo_interactivo. Excluir explícitamente campos avanzados (timeouts, retries, ruta_log, sesion_cookies_path, remote_debug_port, fecha_forzada) de la UI inicial. *Bloquea fase 2.*
3. Documentar regla de ruptura: no compatibilidad automática para JSON legado; si faltan claves en configs antiguas, se confiará en defaults del modelo de configuración en runtime.
4. Fase 2 - Ajustar editor existente (base actual)
5. Mantener como base personio_fichajes/src/editor_config.py y revisar que los campos mostrados y persistidos coincidan 1:1 con el contrato mínimo definido en fase 1. *Depende de 1-3.*
6. Reforzar validación básica en guardar: employee_id entero válido, strings no nulos para textos, booleans explícitos para checks. Mantener reglas complejas fuera de UI y delegarlas a validación del modelo cuando corresponda.
7. Mejorar mensajes de error de guardado para distinguir errores de conversión básica vs. error genérico de I/O.
8. Fase 3 - Verificación funcional y de integración
9. Validar manualmente que el configurador crea/actualiza el JSON en la ruta resuelta por obtener_ruta_config y que el servicio arranca sin cambios adicionales con ese archivo.
10. Ejecutar pruebas de regresión de flujo mínimo: crear config nueva, editar config existente, guardar valores booleanos y horarios, iniciar servicio y confirmar carga correcta.
11. Verificar explícitamente el comportamiento con config antigua no compatible: comprobar fallo legible o defaults aplicados según Configuracion, sin rutina de migración.

**Relevant files**
- c:/repositorio/examples/Python2/personio_fichajes/src/editor_config.py — base del configurador a mantener; revisar campos en self.vars, formulario y guardado.
- c:/repositorio/examples/Python2/personio_fichajes/src/config.py — contrato de Configuracion, defaults y validadores; referencia para límites de alcance de UI mínima.
- c:/repositorio/examples/Python2/personio_fichajes/src/servicio.py — consumo real de configuración al iniciar bot y dependencia de cargar_configuracion.
- c:/repositorio/examples/Python2/personio_fichajes/README.md — actualizar (si aplica) el alcance del configurador v2 y limitaciones de compatibilidad.

**Verification**
1. Ejecutar el configurador y guardar una config mínima válida; confirmar creación de archivo en ruta objetivo devuelta por obtener_ruta_config.
2. Abrir el JSON guardado y comprobar que contiene únicamente el set mínimo definido en fase 1 y tipos correctos.
3. Arrancar servicio Personio y confirmar que cargar_configuracion valida y el proceso avanza a autenticación.
4. Probar error controlado ingresando employee_id no numérico y confirmar mensaje de validación básica en UI.
5. Cargar una config antigua incompleta y verificar comportamiento esperado sin migración (defaults o error claro).

**Decisions**
- Base elegida: personio_fichajes/src/editor_config.py.
- Cobertura: solo campos mínimos para operar.
- Compatibilidad: se aceptan rupturas controladas; sin migración automática.
- Validación de UI: básica (tipos primarios), no reglas completas de negocio.
- En alcance: ajuste del configurador y verificación de integración mínima.
- Fuera de alcance: rediseño completo de UI, pestañas avanzadas, editor de campos avanzados, migrador legado.

**Further Considerations**
1. Definir si se quiere una bandera visible en UI para “modo avanzado” en una siguiente iteración (recomendado: no incluir en esta fase para mantener bajo riesgo).
2. Decidir si se mostrará advertencia explícita en UI al abrir JSON legado con claves no contempladas (recomendado: sí, aviso no bloqueante en iteración posterior).
