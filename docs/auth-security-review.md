# Revisión de seguridad: login y autenticación

Fecha: 2026-11-12. Alcance: login con Google y Supabase en el móvil, almacenamiento de la sesión, cliente HTTP, verificación del JWT en FastAPI y autorización por hogar.

Resumen: la base es sólida, pero hay un fallo de autorización real (un admin que se fue sigue siendo admin) y varias piezas que faltan.

## Lo que está bien hecho

- **Verificación del JWT** ([security.py](../apps/api/src/split_ranch/core/security.py)): solo acepta algoritmos asimétricos, así que `HS256` y `none` quedan rechazados. Exige `exp`, `iss`, `aud` y `sub`, comprueba `role=authenticated` y valida que `sub` sea un UUID. El margen de reloj es de 30 s. La rotación de claves se recoge sola por `kid`.
- **La identidad sale solo del token.** Si alguien no es miembro de un hogar recibe 404, para no revelar que existe. Hay un test de aislamiento entre hogares que se genera desde OpenAPI ([test_tenant_isolation.py](../apps/api/tests/integration/test_tenant_isolation.py)), así que cubre automáticamente las rutas nuevas.
- **En el móvil:** la sesión se guarda en MMKV cifrado, con la clave en SecureStore (Keystore de Android). `detectSessionInUrl: false`, el refresco del token va atado al estado de la app, y la caché de queries se borra al cerrar sesión. Supabase se usa solo para auth y en el bundle no hay secretos.
- **Sin CORS** (correcto para una app solo móvil), Swagger desactivado en prod y códigos de invitación aleatorios con `secrets`.

## 🔴 Fallo real: un admin que se fue sigue siendo admin

[`require_admin`](../apps/api/src/split_ranch/use_cases/common.py) solo mira `role` y no `status`. Cuando un miembro pasa a `left` (`_update_leaving_members` en [periods.py](../apps/api/src/split_ranch/use_cases/periods.py)) su rol no cambia. Además, `_start_leaving` en [households.py](../apps/api/src/split_ranch/use_cases/households.py) deja salir a un admin si queda otro admin.

**Escenario:** el hogar tiene dos admins y uno se va. Cuando su último periodo se liquida pasa a `left`, pero con su token puede seguir:

- generando y revocando invitaciones,
- cambiando roles y expulsando miembros,
- editando el hogar, las categorías y las reglas de reparto,
- reabriendo periodos,
- confirmando transferencias de acreedores que se fueron (`confirm_transfer` en `periods.py`).

Esto contradice la regla de [08-security-and-privacy.md](08-security-and-privacy.md), que dice que un exmiembro solo tiene lectura. En los gastos esto sí se tuvo en cuenta: `_can_edit` en [expenses.py](../apps/api/src/split_ranch/use_cases/expenses.py) comprueba `status != "left"`.

**Arreglo propuesto:** que `require_admin` también rechace a quien tiene `status == "left"`, o pasar el rol a `member` al salir, y añadir un test para este caso.

## 🟠 Riesgos medios

1. **Llamadas sin límite al JWKS con `kid` falsos.** `PyJWKClient` vuelve a descargar el JWKS cada vez que llega un `kid` desconocido. Cualquiera, sin autenticarse, puede mandar tokens con `kid` aleatorios: cada uno provoca una petición saliente a Supabase (con hasta 5 s de timeout) y ocupa un hilo del pool de FastAPI. Es una vía barata para tumbar el servicio. Convendría limitar las recargas (por ejemplo, como mucho una cada 30–60 s) o rechazar el `kid` desconocido hasta la siguiente recarga permitida.
2. **El nonce de Google no se aplica.** En [google.ts](../apps/mobile/src/features/auth/google.ts) la librería antigua no permite meter el nonce en el ID token, así que Supabase no puede comprobarlo. Un ID token de Google interceptado o filtrado podría reutilizarse mientras no caduque. Ya está anotado como TODO (T-0.4, migrar a Credential Manager); conviene hacerlo antes de lanzar.
3. **No hay rate limiting.** La documentación lo pide para auth y para las invitaciones. El código de invitación tiene 40 bits y dura 7 días, lo que hace inviable adivinarlo por fuerza bruta, pero `GET /invitations/{code}` devuelve el nombre del hogar y el número de miembros sin ningún límite de peticiones.

## 🟡 Lo que falta

- **Borrar la cuenta (`DELETE /me`)**: no está implementado y Google Play lo exige ([README de la API](../apps/api/README.md)). Además, `ensure_user` en [users.py](../apps/api/src/split_ranch/use_cases/users.py) no comprueba `deleted_at`. Cuando exista el borrado, un usuario borrado con un token todavía válido podría seguir usando las rutas de hogar durante hasta 1 h.
- **Revocación inmediata**: tras cerrar sesión, el access token sigue valiendo hasta que caduca (≤ 1 h). La documentación lo da por aceptable.
- **Test de que toda ruta exige auth**: la checklist de [08-security-and-privacy.md](08-security-and-privacy.md) lo pide y no existe. El test de aislamiento solo cubre las rutas con `{household_id}`; quedan fuera `/me`, `/households` e `/invitations/...`.
- **Tráfico sin cifrar en Android**: no hay ninguna configuración de `usesCleartextTraffic`. Las builds de release ya bloquean HTTP por defecto, pero conviene dejarlo fijado de forma explícita con `expo-build-properties` y asegurarse de que `EXPO_PUBLIC_API_URL` sea `https` en prod.

## Detalles menores

- **Clave de MMKV** ([storage.ts](../apps/mobile/src/lib/storage.ts)): se generan 16 bytes aleatorios convertidos a 32 caracteres hex. Son 128 bits de entropía, no 256 como dice el comentario. Es suficiente, pero el comentario confunde.
- **`kid` y algoritmo**: se podría comprobar además que `signing_key.algorithm_name == alg`. Es una defensa extra; no se encontró una vía de explotación.
- **`X-Request-ID`** ([main.py](../apps/api/src/split_ranch/main.py)): se toma tal cual del cliente y va a los logs y a Sentry. Convendría validar su longitud y formato.

## Prioridad sugerida

1. Arreglar `require_admin` para exmiembros, con su test.
2. Limitar las recargas del JWKS.
3. Aplicar el nonce de Google (Credential Manager).
4. `DELETE /me` y comprobación de `deleted_at` en `ensure_user`.
5. Rate limiting, test de auth en todas las rutas y configuración explícita contra tráfico sin cifrar.
