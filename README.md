# NullTrace — Antecedentes Judiciales

Versión independiente de NullTrace enfocada únicamente en la consulta de antecedentes judiciales de Colombia. Incluye FastAPI + Playwright, n8n, Telegram y ngrok en contenedores separados.

> Importante: el portal oficial de la Policía Nacional puede exigir reCAPTCHA. Este proyecto **no evade CAPTCHA**. Cuando aparece, el bot entrega el enlace oficial para que la persona termine la consulta de forma manual.

## Estructura

```text
Nulltrace-Antecedentes/
├── docker-compose.yml
├── .env.example
├── microservicio/
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
└── n8n/
    └── workflow.json
```

## 1. Configuración

Desde esta carpeta:

```bash
cp .env.example .env
```

Edita `.env` y completa:

- `NGROK_DOMAIN`: tu dominio reservado, sin `https://`.
- `NGROK_AUTHTOKEN`: token de tu cuenta ngrok.
- `N8N_ENCRYPTION_KEY`: una clave larga que no debes cambiar después.
- `INTERNAL_API_KEY`: otra clave larga y distinta para la comunicación n8n → API.

Puedes generarlas con:

```bash
openssl rand -hex 32
```

No reutilices ni publiques el token actual de tu bot. El archivo `.env` está excluido de Git.

## 2. Levantar contenedores

```bash
docker compose up -d --build
docker compose ps
```

Servicios locales:

- n8n: http://localhost:5679
- API/documentación: http://localhost:5001/docs
- inspector ngrok: http://localhost:4040

La primera vez, abre n8n localmente y crea la cuenta propietaria antes de usar el dominio público.

## 3. Importar y configurar el flujo

1. En n8n abre **Workflows → Import from file**.
2. Importa `n8n/workflow.json`.
3. Crea una credencial **Telegram API** con el token entregado por BotFather.
4. Asigna esa misma credencial a estos cinco nodos: `Telegram Trigger`, `Mensaje de inicio`, `Mensaje de espera`, `Enviar resultado` y `Formato inválido`.
5. Guarda y activa/publica el workflow.

Telegram registrará el webhook usando `https://TU_DOMINIO_NGROK/`. Un mismo bot solo puede tener un webhook activo: usa un bot nuevo si deseas mantener el NullTrace original funcionando al mismo tiempo.

El dominio puede aparecer en varios archivos o carpetas, pero un dominio reservado de ngrok solo puede dirigir un túnel activo a la vez. Detén el túnel del proyecto anterior antes de levantar este, o reserva otro dominio para ejecutar ambos simultáneamente.

## 4. Uso

- `/start` o `/ayuda`: instrucciones.
- Una cédula de 6 a 10 dígitos: inicia la única consulta disponible.
- Puntos, espacios y guiones se limpian antes de validar.
- Cualquier otro dato se rechaza; no hay ramas de teléfono, correo, placa, RUES ni SIMIT.

## Comprobaciones

```bash
curl http://localhost:5001/health
curl -H "X-API-Key: TU_INTERNAL_API_KEY" \
  http://localhost:5001/consultar/antecedentes/1234567890
docker compose logs -f api n8n ngrok
```

No uses una cédula real en pruebas sin autorización. La respuesta esperada normalmente será `verificacion_requerida` si el portal presenta reCAPTCHA.

## Apagar

```bash
docker compose down
```

Esto conserva los datos de n8n. `docker compose down -v` también elimina el volumen y no debe usarse si quieres conservar la configuración.

## Alcance y tratamiento de datos

La consulta oficial está destinada a validar información personal. Usa el bot únicamente con consentimiento o base legal aplicable, limita quién puede acceder al bot y no almacenes resultados más tiempo del necesario. Esta herramienta no reemplaza la certificación ni la interpretación de la Policía Nacional.

No se integran servicios de resolución automática de CAPTCHA. Para una automatización completa debe obtenerse una interfaz o autorización oficial del organismo responsable.

## Publicar en GitHub

Antes de publicar, confirma que `.env` no aparezca en `git status` y que el token de Telegram no esté escrito en ningún archivo. Luego:

Al crear el repositorio desde la web de GitHub usa, por ejemplo:

- **Repository name:** `AntecedentesBot` o `nulltrace-antecedentes`.
- **Description:** `Bot de Telegram para consultar antecedentes judiciales de Colombia con n8n, FastAPI, Playwright, Docker y ngrok.`
- **Visibility:** Public.
- **Add README:** Off.
- **Add .gitignore:** No `.gitignore`.
- **License:** None por ahora, hasta decidir bajo qué condiciones podrán reutilizar el código.

El README y `.gitignore` deben quedar desactivados en el formulario porque ya existen en este proyecto. Así se evita crear un historial remoto incompatible con el commit local.

```bash
git init -b main
git add .
git commit -m "Initial public version"
gh repo create nulltrace-antecedentes --public --source=. --remote=origin --push
```

El último comando requiere tener GitHub CLI instalado y haber ejecutado previamente `gh auth login`. También puedes crear un repositorio vacío desde GitHub y seguir las instrucciones que muestra para conectar el remoto.

Tu compañero podrá clonar el repositorio, crear su propio `.env` desde `.env.example` y configurar su propia credencial de Telegram. No debe recibir una copia de tus secretos.
