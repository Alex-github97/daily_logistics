# Daily Logistics

WMS (almacén), TMS (transporte) y POS (punto de venta), multicliente.
Nació de los módulos homónimos de `control-inventarios`, pero corre como un
proyecto **totalmente independiente**: otros contenedores, otra base de datos,
otra llave de firma de tokens y otros puertos.

## Accesos (local)

| Qué | URL |
|---|---|
| Aplicación (portal de empresas) | http://localhost:5180 |
| Consola maestra (empresas, módulos, usuarios maestros) | http://localhost:5180/admin.html |
| API / Swagger | http://localhost:8100/api/docs |
| pgAdmin (base de datos) | http://localhost:5051 |
| PostgreSQL directo | `localhost:5434`, base `daily_logistics`, usuario `dl_user` (clave en `.env`) |

Primer ingreso (se crea solo en una base vacía; se configura en `.env`):

- Código de empresa: `daily` (es la empresa operadora)
- Usuario: `admin` · Contraseña: `Daily@2026`

## Cómo funciona el multicliente

Igual que en control-inventarios: cada empresa vive en su propio esquema de
PostgreSQL. Desde la consola maestra se crea la empresa (código), se le
activan los módulos contratados (WMS / POS / TMS) y se le crean sus usuarios.
El servidor corta cualquier módulo no contratado aunque se escriba la URL.

## Comandos

```bash
docker compose up -d            # levantar
docker compose logs -f backend  # ver el backend
docker compose down             # detener (los datos quedan en los volúmenes dl_*)
```
