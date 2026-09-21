import asyncio
import hmac
import logging
import os
import re
import unicodedata
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from playwright.async_api import Browser, Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError, async_playwright
from pydantic import BaseModel

from captcha import CaptchaError, solve_page

PORTAL_URL = "https://antecedentes.policia.gov.co:7005/WebJudicial/index.xhtml"
PORTAL_TIMEOUT_MS = int(os.getenv("PORTAL_TIMEOUT_MS", "60000"))
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")
CAPSOLVER_API_KEY = os.getenv("CAPSOLVER_API_KEY", "").strip()
CAPSOLVER_TIMEOUT_SECONDS = min(180, max(1, int(os.getenv("CAPSOLVER_TIMEOUT_SECONDS", "120"))))
CONSULTA_TIMEOUT_SECONDS = 240
CEDULA_PATTERN = re.compile(r"^\d{6,10}$")
NO_PENDIENTES = "NO TIENE ASUNTOS PENDIENTES CON LAS AUTORIDADES JUDICIALES"
PENDIENTES = "ACTUALMENTE NO ES REQUERIDO POR AUTORIDAD JUDICIAL"
logger = logging.getLogger("nulltrace.antecedentes")


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
    motivo: str | None = None
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


def verificacion_requerida(cedula: str, motivo: str) -> Resultado:
    mensajes = {
        "sin_configuracion": "La resolución automática no está configurada. Contacta al administrador del bot.",
        "proveedor_no_disponible": "El servicio de resolución no pudo completar el CAPTCHA. Intenta más tarde.",
        "verificacion_no_confirmada": "El portal no confirmó la verificación automática. Intenta más tarde.",
    }
    return Resultado(
        estado="verificacion_requerida",
        cedula=cedula,
        motivo=motivo,
        mensaje=mensajes[motivo],
    )


async def esperar_resultado(page, timeout: float = 20) -> str | None:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        texto = await texto_resultado(page)
        if texto:
            return texto
        if asyncio.get_running_loop().time() >= deadline:
            return None
        # The CAPTCHA can remain in the DOM while the submission is in flight.
        await page.wait_for_timeout(250)


async def ejecutar_intento(browser: Browser, cedula: str) -> Resultado:
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

        aceptar = page.locator("label[for='aceptaOption:0']").first
        if await aceptar.count():
            # PrimeFaces actualiza el radio y el botón mediante AJAX. Hacer
            # check() directamente sobre el input falla cuando el DOM se
            # vuelve a renderizar; el clic sobre la etiqueta visible sí
            # dispara el evento valueChange oficial.
            await aceptar.click()

        continuar = page.locator("#continuarBtn, button[id='continuarBtn'], input[value*='Enviar']").first
        if await continuar.count():
            await continuar.click()
            await page.wait_for_load_state("domcontentloaded", timeout=PORTAL_TIMEOUT_MS)

        cedula_input = page.locator(
            "#cedulaInput, input[id='cedulaInput'], input[id$='cedulaInput'], input[type='text']"
        ).first
        await cedula_input.fill(cedula)
        await page.wait_for_timeout(1000)

        if await captcha_visible(page):
            if not CAPSOLVER_API_KEY:
                return verificacion_requerida(cedula, "sin_configuracion")
            try:
                await solve_page(page, CAPSOLVER_API_KEY, CAPSOLVER_TIMEOUT_SECONDS)
            except (CaptchaError, PlaywrightError):
                logger.warning("consulta: proveedor_no_disponible")
                return verificacion_requerida(cedula, "proveedor_no_disponible")

        consultar = page.locator(
            "button[type='submit'], input[type='submit'], button:has-text('Consultar')"
        ).first
        await consultar.click()
        texto = await esperar_resultado(page)
        if not texto:
            if await captcha_visible(page):
                logger.warning("consulta: verificacion_no_confirmada")
                return verificacion_requerida(cedula, "verificacion_no_confirmada")
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


async def ejecutar_consulta(browser: Browser, cedula: str) -> Resultado:
    # At most two paid tasks, in fresh sessions, within the endpoint's total budget.
    for intento in range(2):
        resultado = await ejecutar_intento(browser, cedula)
        if resultado.motivo != "verificacion_no_confirmada" or not CAPSOLVER_API_KEY:
            return resultado
        if intento == 0:
            logger.info("consulta: reintento de verificacion con sesion nueva")
    return resultado


@app.get("/consultar/antecedentes/{cedula}", response_model=Resultado)
async def consultar_antecedentes(
    cedula: str,
    _: None = Depends(autorizar),
) -> Resultado:
    if not CEDULA_PATTERN.fullmatch(cedula):
        raise HTTPException(status_code=422, detail="La cédula debe contener entre 6 y 10 dígitos")

    # Include queue time in the budget so n8n always receives a response.
    try:
        async with asyncio.timeout(CONSULTA_TIMEOUT_SECONDS):
            async with app.state.semaforo:
                return await ejecutar_consulta(app.state.browser, cedula)
    except (TimeoutError, PlaywrightTimeoutError, PlaywrightError):
        logger.warning("Tiempo agotado o fallo del navegador durante la consulta")
        return Resultado(
            estado="portal_no_disponible",
            cedula=cedula,
            mensaje="El portal oficial no respondió correctamente. Intenta de nuevo más tarde.",
        )
    except Exception:
        logger.warning("Fallo inesperado durante la consulta")
        return Resultado(
            estado="portal_no_disponible",
            cedula=cedula,
            mensaje="No fue posible completar la consulta en este momento.",
        )
