# Windows con cuenta nueva de n8n y otro dominio de ngrok

Esta instalación reutiliza el código y el workflow, pero crea una cuenta y
credenciales nuevas en n8n. No restaures `n8n-data.tar.gz` de la otra instalación.

Instala Git y [Docker Desktop para Windows](https://docs.docker.com/desktop/setup/install/windows-install/).
Abre Docker Desktop con contenedores Linux y el backend WSL 2. En PowerShell:

```powershell
git clone https://github.com/danielsehuanes07/Antecedentesbot.git
cd Antecedentesbot
Copy-Item .env.example .env
notepad .env
```

Completa los valores de `.env`:

- `NGROK_DOMAIN`: el nuevo dominio asignado o reservado en tu cuenta, sin `https://`.
- `NGROK_AUTHTOKEN`: el token de la cuenta de ngrok propietaria de ese dominio.
- `INTERNAL_API_KEY`: una clave privada larga y aleatoria.
- `CAPSOLVER_API_KEY`: una clave válida con saldo. Puede ser la misma cuenta de CapSolver.

Puedes generar la clave interna desde PowerShell:

```powershell
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()
[BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
```

Copia el resultado a `INTERNAL_API_KEY`, guarda `.env` y enciende los servicios locales:

```powershell
docker compose up -d --build
```

1. Abre `http://localhost:5679/setup` y crea tu cuenta nueva de n8n.
2. Importa `n8n/workflow.json` desde **Import from file**.
3. Crea una credencial **Telegram API** con el token de tu bot de BotFather.
4. Asigna esa credencial a los cinco nodos Telegram: `Telegram Trigger`,
   `Mensaje de inicio`, `Mensaje de espera`, `Enviar resultado` y `Formato inválido`.

Si reutilizas el bot anterior, detén la instancia anterior antes de publicar el
workflow nuevo. Un bot solo tiene un webhook activo, aunque cambies el dominio.
Para ejecutar las dos instalaciones a la vez, usa otro bot y otro dominio de ngrok.

Con la cuenta propietaria ya creada, inicia el túnel:

```powershell
docker compose --profile tunnel up -d ngrok
docker compose --profile tunnel ps
```

Abre `https://TU_NUEVO_DOMINIO`, guarda y publica el workflow. Envía `/start` y
luego una cédula autorizada al bot. CapSolver consume saldo por las tareas de resolución.

Si n8n muestra una cuenta existente, el volumen ya tiene datos: no es una instalación
nueva. No uses `down -v` para borrarlo sin comprobar antes qué contiene.

Cambiar de correo de n8n o dominio de ngrok no cambia el código del microservicio.
La URL del webhook se obtiene de `NGROK_DOMAIN` al crear el contenedor.
