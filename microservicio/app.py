import asyncio
import hmac
import os
import re
import unicodedata
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from playwright.async_api import Browser, Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError, async_playwright
from pydantic import BaseModel

PORTAL_URL = "https://antecedentes.policia.gov.co:7005/WebJudicial/index.xhtml"
PORTAL_TIMEOUT_MS = int(os.getenv("PORTAL_TIMEOUT_MS", "60000"))
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")
CEDULA_PATTERN = re.compile(r"^\d{6,10}$")
NO_PENDIENTES = "NO TIENE ASUNTOS PENDIENTES CON LAS AUTORIDADES JUDICIALES"
PENDIENTES = "ACTUALMENTE NO ES REQUERIDO POR AUTORIDAD JUDICIAL"


class Resultado(BaseModel):
    estado: Literal[
        "sin_asuntos_pendientes",
        "no_requerido",
        "verificacion_requerida",
        "portal_no_disponible",
        "resultado_no_reconocido",
    ]
    cedula: str
    mensaje: str
    resultado: str | None = None
    fuente: str = PORTAL_URL


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    return " ".join(texto.encode("ascii", "ignore").decode().upper().split())


def clasificar_resultado(texto: str) -> str:
    normalizado = normalizar(texto)
    if NO_PENDIENTES in normalizado:
        return "sin_asuntos_pendientes"
    if PENDIENTES in normalizado:
        return "no_requerido"
    return "resultado_no_reconocido"


async def autorizar(x_api_key: str | None = Header(default=None)) -> None:
    if not INTERNAL_API_KEY:
        raise HTTPException(status_code=503, detail="INTERNAL_API_KEY no configurada")
    if not x_api_key or not hmac.compare_digest(x_api_key, INTERNAL_API_KEY):
        raise HTTPException(status_code=401, detail="No autorizado")


@asynccontextmanager
async def lifespan(app: FastAPI):
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
    )
    app.state.browser = browser
    app.state.semaforo = asyncio.Semaphore(1)
    yield
    await browser.close()
    await playwright.stop()


app = FastAPI(
    title="NullTrace Antecedentes",
    version="1.0.0",
    description="Consulta enfocada exclusivamente en antecedentes judiciales de Colombia.",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def texto_resultado(page) -> str | None:
    selectores = [
        "#form\\:mensajeCiudadano",
        "#form\\:mensajeCiudadano span",
        "[id$='mensajeCiudadano']",
        "text=/NO TIENE ASUNTOS PENDIENTES|ACTUALMENTE NO ES REQUERIDO/i",
    ]
    for selector in selectores:
        locator = page.locator(selector).first
        try:
            if await locator.count() and await locator.is_visible(timeout=1000):
                texto = (await locator.inner_text()).strip()
                if texto:
                    return texto
        except PlaywrightError:
            continue
    return None


async def captcha_visible(page) -> bool:
    selectores = [
        "iframe[src*='recaptcha']",
        ".g-recaptcha",
        "textarea[name='g-recaptcha-response']",
        "text=/No soy un robot/i",
    ]
    for selector in selectores:
        try:
            if await page.locator(selector).count():
                return True
        except PlaywrightError:
            continue
    return False


async def ejecutar_consulta(browser: Browser, cedula: str) -> Resultado:
    context = await browser.new_context(
        locale="es-CO",
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        ),
    )
    page = await context.new_page()
    page.set_default_timeout(15000)

    try:
        await page.goto(PORTAL_URL, timeout=PORTAL_TIMEOUT_MS, wait_until="domcontentloaded")

        aceptar = page.locator("#aceptaOption\\:0, input[id='aceptaOption:0']").first
        if await aceptar.count():
            await aceptar.check(force=True)

        continuar = page.locator("#continuarBtn, button[id='continuarBtn'], input[value*='Enviar']").first
        if await continuar.count():
            await continuar.click()
            await page.wait_for_load_state("domcontentloaded", timeout=PORTAL_TIMEOUT_MS)

        cedula_input = page.locator(
            "#cedulaInput, input[id='cedulaInput'], input[id$='cedulaInput'], input[type='text']"
        ).first
        await cedula_input.fill(cedula)
        await page.wait_for_timeout(1000)

        # El portal oficial suele exigir reCAPTCHA. No se intenta evadirlo.
        if await captcha_visible(page):
            return Resultado(
                estado="verificacion_requerida",
                cedula=cedula,
                mensaje=(
                    "El portal oficial exige completar la verificación 'No soy un robot'. "
                    "Abre el enlace oficial para finalizar la consulta personalmente."
                ),
            )

        consultar = page.locator(
            "button[type='submit'], input[type='submit'], button:has-text('Consultar')"
        ).first
        await consultar.click()
        await page.wait_for_timeout(2500)

        texto = await texto_resultado(page)
        if not texto:
            return Resultado(
                estado="resultado_no_reconocido",
                cedula=cedula,
                mensaje="El portal respondió, pero su formato cambió y no se pudo interpretar.",
            )

        estado = clasificar_resultado(texto)
        return Resultado(
            estado=estado,
            cedula=cedula,
            mensaje="Consulta realizada en el portal oficial de la Policía Nacional.",
            resultado=texto,
        )
    finally:
        await context.close()


@app.get("/consultar/antecedentes/{cedula}", response_model=Resultado)
async def consultar_antecedentes(
    cedula: str,
    _: None = Depends(autorizar),
) -> Resultado:
    if not CEDULA_PATTERN.fullmatch(cedula):
        raise HTTPException(status_code=422, detail="La cédula debe contener entre 6 y 10 dígitos")

    async with app.state.semaforo:
        try:
            return await ejecutar_consulta(app.state.browser, cedula)
        except (PlaywrightTimeoutError, PlaywrightError):
            return Resultado(
                estado="portal_no_disponible",
                cedula=cedula,
                mensaje="El portal oficial no respondió correctamente. Intenta de nuevo más tarde.",
            )
        except Exception:
            return Resultado(
                estado="portal_no_disponible",
                cedula=cedula,
                mensaje="No fue posible completar la consulta en este momento.",
            )
