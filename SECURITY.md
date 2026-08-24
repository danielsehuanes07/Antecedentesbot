# Seguridad

## Secretos

Nunca publiques ni confirmes en Git:

- tokens de bots de Telegram;
- `NGROK_AUTHTOKEN`;
- `N8N_ENCRYPTION_KEY`;
- `INTERNAL_API_KEY`;
- el archivo `.env` ni el volumen de datos de n8n.

Si un token aparece en una captura, chat, commit o log público, debe considerarse comprometido. Revócalo en el servicio correspondiente y genera uno nuevo. Borrarlo de un commit posterior no es suficiente porque continúa en el historial de Git.

## Uso del bot

La consulta trata información personal sensible. Restringe el acceso al bot, consulta únicamente información propia o autorizada y evita conservar resultados en logs o historiales más tiempo del necesario.

## CAPTCHA

El proyecto no integra servicios para evadir CAPTCHA. Si el portal oficial exige una comprobación humana, el bot dirige al usuario a la fuente oficial para finalizarla.
