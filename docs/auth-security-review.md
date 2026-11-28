# Revisión de seguridad: login y autenticación

Fecha: 2026-11-12. Alcance: login con Google y Supabase en el móvil, almacenamiento de la sesión, cliente HTTP, verificación del JWT en FastAPI y autorización por grupo.

> **Nota (2026-11-17):** esta revisión es anterior a la migración 0006 (grupos sin periodos). Los periodos, `periods.py`, `confirm_transfer` y el estado `leaving` ya no existen; el hallazgo del admin que se fue quedó resuelto (los miembros `left` reciben 404 y hay un único admin activo por grupo).

Resumen: la base es sólida, pero hay un fallo de autorización real (un admin que se fue sigue siendo admin) y varias piezas que faltan.

## Lo que está bien hecho

- **Verificación del JWT** ([security.py](../apps/api/src/split_ranch/core/security.py)): solo acepta algoritmos asimétricos, así que `HS256` y `none` quedan rechazados. Exige `exp`, `iss`, `aud` y `sub`, comprueba `role=authenticated` y valida que `sub` sea un UUID. El margen de reloj es de 30 s. La rotación de claves se recoge sola por `kid`.
- **La identidad sale solo del token.** Si alguien no es miembro de un grupo recibe 404, para no revelar que existe. Hay un test de aislamiento entre grupoes que se genera desde OpenAPI ([test_tenant_isolation.py](../apps/api/tests/integration/test_tenant_isolation.py)), así que cubre automáticamente las rutas nuevas.
- **En el móvil:** la sesión se guarda en MMKV cifrado, con la clave en SecureStore (Keystore de Android). `detectSessionInUrl: false`, el refresco del token va atado al estado de la app, y la caché de queries se borra al cerrar sesión. Supabase se usa solo para auth y en el bundle no hay secretos.
- **Sin CORS** (correcto para una app solo móvil), Swagger desactivado en prod y códigos de invitación aleatorios con `secrets`.

## 🔴 Fallo real: un admin que se fue sigue siendo admin

[`require_admin`](../apps/api/src/split_ranch/use_cases/common.py) solo mira `role` y no `status`. Cuando un miembro pasa a `left` (`_update_leaving_members` en [periods.py](../apps/api/src/split_ranch/use_cases/periods.py)) su rol no cambia. Además, `_start_leaving` en [groups.py](../apps/api/src/split_ranch/use_cases/groups.py) deja salir a un admin si queda otro admin.

**Escenario:** el grupo tiene dos admins y uno se va. Cuando su último periodo se liquida pasa a `left`, pero con su token puede seguir:

- generando y revocando invitaciones,
- cambiando roles y expulsando miembros,
- editando el grupo, las categorías y las reglas de reparto,
- reabriendo periodos,
- confirmando transferencias de acreedores que se fueron (`confirm_transfer` en `periods.py`).

Esto contradice la regla de [08-security-and-privacy.md](08-security-and-privacy.md), que dice que un exmiembro solo tiene lectura. En los gastos esto sí se tuvo en cuenta: `_can_edit` en [expenses.py](../apps/api/src/split_ranch/use_cases/expenses.py) comprueba `status != "left"`.

**✅ Corregido (2026-11-12):** `GroupActor.is_admin` ([actor.py](../apps/api/src/split_ranch/core/actor.py)) ahora devuelve `False` cuando `status == "left"`, lo que cubre `require_admin`, `confirm_transfer` y `_can_edit`. El rol guardado se conserva por historial. Test: `test_former_admin_loses_admin_rights` en [test_groups.py](../apps/api/tests/integration/test_groups.py).

**Actualización (2026-11-27):** `get_group_actor` ya devuelve 404 a todo miembro que no esté activo, así que ese chequeo, `require_active` y `can_edit` dependiente del estado nunca se activaban. Se quitaron junto con `GroupActor.status`: la única barrera es `get_group_actor`, y el docstring de `GroupActor` deja escrito que solo esa dependencia lo construye. El test citado arriba ya no existía; lo reemplaza `test_former_admin_cannot_write_anything` en [test_groups.py](../apps/api/tests/integration/test_groups.py), que comprueba el 404 en escrituras de cada router.

## 🟠 Riesgos medios

1. **Llamadas sin límite al JWKS con `kid` falsos.** `PyJWKClient` vuelve a descargar el JWKS cada vez que llega un `kid` desconocido. Cualquiera, sin autenticarse, puede mandar tokens con `kid` aleatorios: cada uno provoca una petición saliente a Supabase (con hasta 5 s de timeout) y ocupa un hilo del pool de FastAPI. Es una vía barata para tumbar el servicio. Convendría limitar las recargas (por ejemplo, como mucho una cada 30–60 s) o rechazar el `kid` desconocido hasta la siguiente recarga permitida.

   **✅ Mitigado (2026-11-12):** desde la 2.14.0 PyJWT aplica un cooldown a las recargas por `kid` desconocido (GHSA-2gx3-rcp4-g85q). Cambios hechos:
   - Versión mínima subida a `PyJWT>=2.15.1` en `pyproject.toml`.
   - `cooldown_duration=30` explícito en [security.py](../apps/api/src/split_ranch/core/security.py).
   - Quitado `cache_keys`: era un LRU sin caducidad que impedía revocar claves. Ahora el JWKS se cachea 600 s, como recomienda Supabase.
   - `verify()` rechaza tokens sin `kid` o con un `kid` de más de 128 caracteres antes de consultar las claves.

   Tests en [test_jwks_refetch.py](../apps/api/tests/unit/test_jwks_refetch.py), con un `PyJWKClient` real: límite de recargas, rotación de clave, revocación al caducar la caché y `kid` inválido.

2. **El nonce de Google no se aplica.** En [google.ts](../apps/mobile/src/features/auth/google.ts) la librería antigua no permite meter el nonce en el ID token, así que Supabase no puede comprobarlo. Un ID token de Google interceptado o filtrado podría reutilizarse mientras no caduque. Conviene hacerlo antes de lanzar.

   **✅ Corregido (2026-11-12, login probado en el emulador Android con el dev-client):** se migró a `react-native-nitro-google-signin` (MIT, Credential Manager), que mete `SHA256(nonce)` en el ID token. Cambios:
   - En cada intento se llama a `configure({ nonce })`, y Supabase recibe siempre el nonce original.
   - Si el claim `nonce` del token no coincide, la app lo rechaza antes de mandarlo. Esto importa porque Supabase acepta tokens sin nonce cuando la petición tampoco lo trae.
   - Los intentos de login se serializan.

   Tests en [google.test.ts](../apps/mobile/src/features/auth/google.test.ts). Queda pendiente: probar en un teléfono físico y con un build de EAS (con su SHA-1 registrado).

3. **No hay rate limiting.** La documentación lo pide para auth y para las invitaciones. El código de invitación tiene 40 bits y dura 7 días, lo que hace inviable adivinarlo por fuerza bruta, pero `GET /invitations/{code}` devuelve el nombre del grupo y el número de miembros sin ningún límite de peticiones.

## 🟡 Lo que falta

- **Borrar la cuenta (`DELETE /me`)**: no está implementado y Google Play lo exige ([README de la API](../apps/api/README.md)). Además, `ensure_user` en [users.py](../apps/api/src/split_ranch/use_cases/users.py) no comprueba `deleted_at`. Cuando exista el borrado, un usuario borrado con un token todavía válido podría seguir usando las rutas de grupo durante hasta 1 h.
- **Revocación inmediata**: tras cerrar sesión, el access token sigue valiendo hasta que caduca (≤ 1 h). La documentación lo da por aceptable.
- **Test de que toda ruta exige auth**: la checklist de [08-security-and-privacy.md](08-security-and-privacy.md) lo pide y no existe. El test de aislamiento solo cubre las rutas con `{group_id}`; quedan fuera `/me`, `/groups` e `/invitations/...`.
- **Tráfico sin cifrar en Android**: no hay ninguna configuración de `usesCleartextTraffic`. Las builds de release ya bloquean HTTP por defecto, pero conviene dejarlo fijado de forma explícita con `expo-build-properties` y asegurarse de que `EXPO_PUBLIC_API_URL` sea `https` en prod.

## Detalles menores

- **Clave de MMKV** ([storage.ts](../apps/mobile/src/lib/storage.ts)): se generan 16 bytes aleatorios convertidos a 32 caracteres hex. Son 128 bits de entropía, no 256 como dice el comentario. Es suficiente, pero el comentario confunde.
- **`kid` y algoritmo**: se podría comprobar además que `signing_key.algorithm_name == alg`. Es una defensa extra; no se encontró una vía de explotación.
- **`X-Request-ID`** ([main.py](../apps/api/src/split_ranch/main.py)): se toma tal cual del cliente y va a los logs y a Sentry. Convendría validar su longitud y formato. **Hecho:** solo se acepta `^[A-Za-z0-9-]{1,64}$`; si no cumple, se genera uno nuevo.

## Prioridad sugerida

1. ~~Arreglar `require_admin` para exmiembros, con su test.~~ Hecho.
2. ~~Limitar las recargas del JWKS.~~ Hecho.
3. ~~Aplicar el nonce de Google (Credential Manager).~~ Hecho; probado en emulador.
4. `DELETE /me` y comprobación de `deleted_at` en `ensure_user`.
5. Rate limiting, test de auth en todas las rutas y configuración explícita contra tráfico sin cifrar.
