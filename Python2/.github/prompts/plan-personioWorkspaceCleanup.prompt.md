## Plan: Limpieza Segura Fuera de personio_fichajes

Reducir el ruido del workspace sin romper operación ni recuperación. En vez de borrar en bloque, aplicar limpieza por fases con verificación entre fases: primero artefactos seguros, después elementos legacy opcionales, y por último secretos/entornos solo con confirmación explícita.

**Steps**
1. Fase 1 - Inventario y clasificación final por riesgo (completado en análisis): KEEP / REVIEW / DELETE CANDIDATE de todo lo que está fuera de personio_fichajes.
2. Fase 2 - Alineación de alcance con el usuario: confirmar si se mantiene compatibilidad con flujo legacy (`src`, `Setup`, `.bat` de raíz, `README.txt`) o si el alcance queda solo en personio_fichajes.
3. Fase 3 - Limpieza segura inicial (paralela entre sí): eliminar únicamente artefactos de bajo riesgo (`__pycache__`, opcionalmente `.vscode`, `.github`, `copilot-instructions.md`) según aprobación.
4. Fase 4 - Verificación post-limpieza inicial: ejecutar servicio actual de personio_fichajes con `SOLO_FECHA` y validar salida/logs.
5. Fase 5 - Limpieza legacy condicional (depende de 2 y 4): eliminar o archivar `src`, `Setup`, `.bat` de raíz y `README.txt` solo si el usuario confirma que no se usan para operación/scheduler.
6. Fase 6 - Higiene de secretos y sesión (depende de 2): decidir política para `.env`, `cookies.pkl`, `token_csrf.txt` (mantener, mover a personio_fichajes o eliminar) minimizando exposición.
7. Fase 7 - Verificación final: confirmar que quedan solo elementos necesarios para operación diaria y documentar el nuevo “mínimo viable” del repo.

**Relevant files**
- `personio_fichajes/src/servicio.py` — punto de entrada actual para validar ejecución tras limpieza.
- `personio_fichajes/src/config.py` — confirma que el runtime/carga de entorno es autocontenido en personio_fichajes.
- `ejecutar_servicio_exe.bat` — posible dependencia operativa legacy en tareas programadas.
- `ejecutar_servicio_script.bat` — posible dependencia operativa legacy en tareas programadas.
- `iniciar_servicio.bat` — posible dependencia operativa legacy en tareas programadas.
- `src/` — código legacy completo fuera de personio_fichajes.
- `Setup/` — bootstrap legacy de dependencias.
- `.env` — potencial secreto local (alto cuidado).
- `cookies.pkl` — artefacto de sesión sensible.
- `token_csrf.txt` — artefacto/token sensible.

**Verification**
1. Antes de borrar: confirmar por escrito el alcance (solo personio_fichajes o compatibilidad legacy).
2. Después de Fase 3: ejecutar `python -m src.servicio` dentro de personio_fichajes y validar que no hay regresiones.
3. Si se elimina legacy: revisar que no existan tareas Windows/NSSM apuntando a `.bat` de raíz.
4. Después de limpieza final: listar raíz y comprobar que todo lo restante tiene propósito operativo/documental claro.

**Decisions**
- Confirmado por el usuario: conservar compatibilidad legacy fuera de personio_fichajes (`src`, `Setup`, `.bat` y `README.txt` no se borran en esta ronda).
- Confirmado por el usuario: aplicar limpieza máxima en lo no-legacy.
- Confirmado por el usuario: eliminar secretos/artefactos sensibles de nivel superior (`.env`, `cookies.pkl`, `token_csrf.txt`).
- Excluido: tocar contenido interno de personio_fichajes en esta tarea.

**Further Considerations**
1. Recomendación: en vez de borrar inmediatamente `src`/`Setup`, mover primero a carpeta de archivo temporal para rollback rápido.
2. Recomendación: definir una política explícita de secretos (`.env`, cookies, tokens) antes de limpiar.
3. Recomendación: después de limpiar, dejar un README corto de operación real para evitar volver a mezclar flujos legacy con el actual.
