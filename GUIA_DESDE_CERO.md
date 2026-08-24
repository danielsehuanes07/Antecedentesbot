# Guía rápida desde cero

Necesitas tener Docker instalado, un bot creado con BotFather y una cuenta de ngrok con dominio reservado.

## Primera instalación

### 1. Clonar el proyecto

```bash
git clone https://github.com/danielsehuanes07/Antecedentesbot.git
```

```bash
cd Antecedentesbot
```

### 2. Crear la configuración privada

```bash
cp .env.example .env
```

Genera la clave interna:

```bash
openssl rand -hex 32
```

Abre el archivo:

```bash
nano .env
```

Reemplaza los tres primeros valores:

```env
NGROK_DOMAIN=tu-dominio-reservado.ngrok-free.app
NGROK_AUTHTOKEN=tu-authtoken-de-ngrok
INTERNAL_API_KEY=la-clave-generada-con-openssl
GENERIC_TIMEZONE=America/Bogota
TZ=America/Bogota
```

- Copia el authtoken desde <https://dashboard.ngrok.com/get-started/your-authtoken>.
- Copia el dominio desde <https://dashboard.ngrok.com/domains>.
- Escribe el dominio sin `https://`.
- Guarda en nano con `Ctrl+O`, `Enter` y sal con `Ctrl+X`.

### 3. Iniciar la API y n8n

```bash
docker compose up -d --build
```

```bash
docker compose ps
```

Abre <http://localhost:5679> y crea la cuenta propietaria de n8n.

### 4. Configurar el bot en n8n

1. Selecciona **Import from file** e importa `n8n/workflow.json`.
2. Abre `Telegram Trigger`.
3. Crea una credencial **Telegram API** y pega el token de BotFather.
4. Selecciona esa credencial en los demás nodos de Telegram si n8n no lo hace automáticamente.
5. Guarda y publica el workflow.

### 5. Iniciar ngrok

```bash
docker compose --profile tunnel up -d ngrok
```

```bash
docker compose --profile tunnel ps
```

Comprueba el túnel en <http://localhost:4040>. Después abre el bot de Telegram y envía `/start`.

## Uso diario

Para encender todo:

```bash
cd Antecedentesbot
```

```bash
docker compose up -d
```

```bash
docker compose --profile tunnel up -d ngrok
```

Para apagar todo sin borrar la configuración:

```bash
docker compose --profile tunnel down
```

No uses `docker compose down -v`: la opción `-v` elimina las cuentas, credenciales y workflows guardados en n8n.

## Resultado actual

El bot recibe la cédula y avanza hasta el reCAPTCHA del portal oficial. Cuando aparece, entrega el enlace para completar la verificación personalmente.
