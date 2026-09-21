import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from playwright.async_api import async_playwright

import app
import captcha


class Response:
    ok = True

    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        return self.payload


class SolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_only_unconfirmed_verification(self):
        failed = app.verificacion_requerida("1234567890", "verificacion_no_confirmada")
        success = app.Resultado(estado="sin_asuntos_pendientes", cedula="1234567890", mensaje="ok")
        with patch.object(app, "CAPSOLVER_API_KEY", "secret"), patch.object(app, "ejecutar_intento", new_callable=AsyncMock, side_effect=[failed, success]) as attempt:
            self.assertEqual((await app.ejecutar_consulta(None, "1234567890")).estado, success.estado)
            self.assertEqual(attempt.await_count, 2)

    async def test_retry_is_bounded_and_provider_failure_not_retried(self):
        for reason, count in [("verificacion_no_confirmada", 2), ("proveedor_no_disponible", 1), ("sin_configuracion", 1)]:
            with patch.object(app, "CAPSOLVER_API_KEY", "secret"), patch.object(app, "ejecutar_intento", new_callable=AsyncMock, return_value=app.verificacion_requerida("1234567890", reason)) as attempt:
                await app.ejecutar_consulta(None, "1234567890")
                self.assertEqual(attempt.await_count, count)

    async def test_polling_returns_token_and_creates_only_one_task(self):
        request = AsyncMock()
        request.post.side_effect = [
            Response({"errorId": 0, "taskId": "task"}),
            Response({"errorId": 0, "status": "processing"}),
            Response({"errorId": 0, "status": "ready", "solution": {"gRecaptchaResponse": "token"}}),
        ]
        with patch("captcha.asyncio.sleep", new_callable=AsyncMock):
            self.assertEqual(await captcha.solve_with_request(request, "secret", {"websiteKey": "key"}), "token")
        methods = [call.args[0].rsplit("/", 1)[-1] for call in request.post.call_args_list]
        self.assertEqual(methods, ["createTask", "getTaskResult", "getTaskResult"])

    async def test_provider_error_does_not_leak_response_or_retry(self):
        request = AsyncMock()
        request.post.return_value = Response({"errorId": 1, "errorDescription": "secret"})
        with self.assertRaisesRegex(captcha.CaptchaError, "^provider_error$"):
            await captcha.solve_with_request(request, "secret", {})
        self.assertEqual(request.post.await_count, 1)

    async def test_ready_without_token_is_failure(self):
        request = AsyncMock()
        request.post.return_value = Response({"errorId": 0, "status": "ready", "solution": {}})
        with self.assertRaisesRegex(captcha.CaptchaError, "missing_token"):
            await captcha.solve_with_request(request, "secret", {})

    async def test_missing_task_id_is_failure(self):
        request = AsyncMock()
        request.post.return_value = Response({"errorId": 0})
        with self.assertRaisesRegex(captcha.CaptchaError, "invalid_task"):
            await captcha.solve_with_request(request, "secret", {})

    async def test_http_error_is_failure(self):
        request = AsyncMock()
        response = Response({})
        response.ok = False
        request.post.return_value = response
        with self.assertRaisesRegex(captcha.CaptchaError, "provider_http_error"):
            await captcha.solve_with_request(request, "secret", {})

    async def test_timeout_is_bounded(self):
        async def slow(*args):
            await asyncio.sleep(5)
        with patch("captcha.solve_with_request", side_effect=slow):
            with self.assertRaisesRegex(captcha.CaptchaError, "timeout"):
                await captcha.solve("secret", {}, 1)


class BrowserTests(unittest.IsolatedAsyncioTestCase):
    async def test_waits_for_delayed_result_while_captcha_still_present(self):
        await self.page.set_content('''<textarea name="g-recaptcha-response"></textarea>
            <script>setTimeout(() => { document.body.innerHTML =
            '<span id="form:mensajeCiudadano">NO TIENE ASUNTOS PENDIENTES CON LAS AUTORIDADES JUDICIALES</span>';
            }, 3000);</script>''')
        text = await app.esperar_resultado(self.page, timeout=5)
        self.assertEqual(app.clasificar_resultado(text), "sin_asuntos_pendientes")

    async def asyncSetUp(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(args=["--no-sandbox"])
        self.page = await self.browser.new_page()
        await self.page.route("**/*", lambda route: route.fulfill(body="<html></html>", content_type="text/html"))
        await self.page.goto("https://example.test/form?cedula=1234567890")

    async def asyncTearDown(self):
        await self.browser.close()
        await self.playwright.stop()

    async def test_token_applied_and_callback_called_without_sending_identity(self):
        await self.page.set_content('''
            <div class="g-recaptcha" data-sitekey="public-key" data-callback="onCaptcha"></div>
            <textarea name="g-recaptcha-response"></textarea>
            <script>window.onCaptcha = token => window.receivedToken = token;</script>
        ''')
        with patch("captcha.solve", new_callable=AsyncMock, return_value="solved") as solve:
            await captcha.solve_page(self.page, "secret", 120)
        task = solve.call_args.args[1]
        self.assertEqual(task["websiteURL"], "https://example.test/form")
        self.assertEqual(task["websiteKey"], "public-key")
        self.assertEqual(await self.page.locator("textarea").input_value(), "solved")
        self.assertEqual(await self.page.evaluate("window.receivedToken"), "solved")

    async def test_unsupported_captcha_does_not_create_paid_task(self):
        with patch("captcha.solve", new_callable=AsyncMock) as solve:
            with self.assertRaisesRegex(captcha.CaptchaError, "unsupported_captcha"):
                await captcha.solve_page(self.page, "secret", 120)
            solve.assert_not_awaited()

    async def test_consultation_fallback_and_success(self):
        form = '''<input id="cedulaInput"><div class="g-recaptcha" data-sitekey="key"></div>
            <textarea name="g-recaptcha-response"></textarea>
            <button type="submit" onclick="document.body.innerHTML =
            '<span id=&quot;form:mensajeCiudadano&quot;>NO TIENE ASUNTOS PENDIENTES CON LAS AUTORIDADES JUDICIALES</span>'">Consultar</button>'''
        await self.browser.close()
        self.browser = await self.playwright.chromium.launch(args=["--no-sandbox"])
        original = self.browser.new_context

        async def context_with_form(**kwargs):
            context = await original(**kwargs)
            await context.route("**/*", lambda route: route.fulfill(body=form, content_type="text/html"))
            return context

        with patch.object(self.browser, "new_context", side_effect=context_with_form):
            with patch.object(app, "CAPSOLVER_API_KEY", ""), patch.object(app, "solve_page", new_callable=AsyncMock) as solve:
                result = await app.ejecutar_consulta(self.browser, "1234567890")
                self.assertEqual(result.estado, "verificacion_requerida")
                solve.assert_not_awaited()
            with patch.object(app, "CAPSOLVER_API_KEY", "secret"):
                with patch.object(app, "solve_page", side_effect=captcha.CaptchaError("provider_error")):
                    result = await app.ejecutar_consulta(self.browser, "1234567890")
                    self.assertEqual(result.estado, "verificacion_requerida")
                with patch("captcha.solve", new_callable=AsyncMock, return_value="solved"):
                    result = await app.ejecutar_consulta(self.browser, "1234567890")
                    self.assertEqual(result.estado, "sin_asuntos_pendientes")


if __name__ == "__main__":
    unittest.main()
