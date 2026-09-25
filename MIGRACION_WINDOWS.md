# Continuar en Windows con la misma cuenta y configuración

Si quieres **otra cuenta de n8n y otro dominio de ngrok**, sigue
[Windows con cuenta nueva](WINDOWS_CUENTA_NUEVA.md) y no restaures esta copia.

El repositorio contiene el código y el workflow de plantilla. La cuenta de n8n,
las credenciales de Telegram, el workflow publicado y las ejecuciones están en
el volumen `n8n_data`. Para conservarlos necesitas también la copia privada.

La copia preparada el 25 de septiembre de 2026 está en
`n8n/backups/windows-20260925/` y contiene:

- `.env`: configuración privada de ngrok, la API y CapSolver.
- `n8n-data.tar.gz`: volumen de n8n, incluida su clave de cifrado.
- `SHA256SUMS`: huellas para comprobar la transferencia.

Esta carpeta está excluida de Git. Transfiérela directamente a tu equipo Windows
(por ejemplo, con una memoria USB). Contiene secretos e historial de consultas;
no la subas al repositorio. Las modificaciones posteriores a esta copia no se
trasladan automáticamente.

## 1. Preparar Windows

Instala Git y [Docker Desktop para Windows](https://docs.docker.com/desktop/setup/install/windows-install/).
Inicia Docker Desktop con contenedores Linux, usando el backend WSL 2. Ejecuta
los siguientes comandos en **PowerShell**, en la carpeta donde guardarás el proyecto:

```powershell
git clone https://github.com/danielsehuanes07/Antecedentesbot.git
cd Antecedentesbot
docker version
docker compose version
```

Si ya lo clonaste, entra en esa carpeta y usa `git pull --ff-only`.

## 2. Copiar los datos privados

Copia la carpeta privada completa dentro del clon, con esta estructura:

```text
Antecedentesbot/
  docker-compose.yml
  n8n/backups/windows-20260925/
    .env
    n8n-data.tar.gz
    SHA256SUMS
```

Verifica los archivos y copia la configuración al directorio del proyecto:

```powershell
Get-ChildItem -Force .\n8n\backups\windows-20260925
Get-FileHash .\n8n\backups\windows-20260925\n8n-data.tar.gz -Algorithm SHA256
Get-Content .\n8n\backups\windows-20260925\SHA256SUMS
Copy-Item .\n8n\backups\windows-20260925\.env .\.env
```

El hash del archivo comprimido debe coincidir con su entrada en `SHA256SUMS`.
No inicies n8n ni registres otra cuenta antes de restaurar.

## 3. Restaurar en un volumen nuevo

Desde la raíz del proyecto en PowerShell, ejecuta este comando en una sola línea:

```powershell
docker compose run --rm --no-deps --user root --entrypoint sh -v "${PWD}/n8n/backups/windows-20260925:/backup:ro" n8n -c 'test ! -e /home/node/.n8n/database.sqlite && tar -xzf /backup/n8n-data.tar.gz -C /home/node/.n8n && chown -R node:node /home/node/.n8n'
```

Docker crea el volumen y restaura sus archivos sin iniciar el servidor de n8n.
Comprueba que termine sin errores. Si devuelve un código distinto de cero,
detente: puede existir una base de datos previa o haber fallado la restauración.
El comando rechaza sobrescribir una base de datos existente. No borres ese volumen
si ya tiene información que quieras conservar.

## 4. Cambiar de equipo e iniciar

Antes de arrancar Windows, detén el proyecto en Linux:

```bash
docker compose --profile tunnel stop
```

El mismo bot de Telegram y dominio ngrok deben estar activos en un solo equipo.
Después, en Windows:

```powershell
docker compose --profile tunnel up -d --build
docker compose --profile tunnel ps
Invoke-RestMethod http://localhost:5001/health
```

Abre `http://localhost:5679` o tu dominio de ngrok. Entra con **la misma cuenta y
contraseña de n8n que tenías al crear la copia**. No es necesario importar el
workflow ni configurar de nuevo Telegram. Si aparece el registro de propietario,
la copia no se restauró en el volumen que está usando esa instancia.

Comprueba que el workflow esté publicado. Envía `/start` al bot y luego una cédula
autorizada; revisa la ejecución en n8n. Las consultas pueden consumir hasta dos
tareas de CapSolver.

Para ver logs y apagar, respectivamente:

```powershell
docker compose logs -f api n8n ngrok
docker compose --profile tunnel down
```

No uses `down -v`: elimina los datos persistentes de n8n.

La integridad de SQLite y la presencia de la clave de cifrado en la copia se
verificaron en Linux. La restauración y el arranque final en Windows deben
comprobarse en ese equipo.
