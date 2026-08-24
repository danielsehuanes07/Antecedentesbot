# Guía desde cero

## Requisitos

- Docker y Docker Compose.
- Una cuenta de ngrok con authtoken y dominio reservado.
- Un bot nuevo creado con BotFather.

## 1. Clonar y configurar

```bash
git clone https://github.com/danielsehuanes07/Antecedentesbot.git
cd Antecedentesbot
cp .env.example .env
openssl rand -hex 32
```

Edita `.env`:

```env
NGROK_DOMAIN=dominio-propio.ngrok-free.app
NGROK_AUTHTOKEN=authtoken-propio
INTERNAL_API_KEY=resultado_de_openssl_rand
GENERIC_TIMEZONE=America/Bogota
TZ=America/Bogota
```

El authtoken se copia desde el panel de ngrok, en **Getting Started → Your Authtoken**. El dominio se obtiene en **Domains**. Cada persona debe usar los valores de su propia cuenta.

## 2. Iniciar n8n y la API

```bash
docker compose up -d --build
docker compose ps
```

Abre `http://localhost:5679` y crea la cuenta propietaria de n8n.

## 3. Preparar el workflow

1. En n8n selecciona **Import from file**.
2. Importa `n8n/workflow.json`.
3. Crea una credencial **Telegram API** con el token de BotFather.
4. Selecciona esa credencial en `Telegram Trigger` y en los nodos que envían mensajes.
5. Guarda y activa/publica el workflow.

## 4. Iniciar ngrok

```bash
docker compose --profile tunnel up -d ngrok
```

Comprueba el túnel en `http://localhost:4040`. Luego abre el bot y envía `/start`.

## 5. Uso diario

Después de la primera configuración:

```bash
docker compose up -d
docker compose --profile tunnel up -d ngrok
```

Para apagar todo:

```bash
docker compose --profile tunnel down
```

Los workflows, el propietario y las credenciales permanecen en el volumen Docker `n8n_data`.

## Estado esperado de la consulta

El bot recibe una cédula, abre el portal oficial y avanza hasta la verificación reCAPTCHA. Si aparece, responde `verificacion_requerida` y entrega el enlace oficial. El proyecto no resuelve automáticamente esa verificación.
