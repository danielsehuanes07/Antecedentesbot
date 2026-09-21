"""Optional reCAPTCHA v2 integration; one paid task per attempt at most."""

import asyncio

from playwright.async_api import Error as PlaywrightError, async_playwright


class CaptchaError(Exception):
    """A sanitized failure, safe to log without provider responses or tokens."""


async def solve_with_request(request, api_key: str, task: dict) -> str:
    async def post(method, data):
        response = await request.post(
            f"https://api.capsolver.com/{method}",
            data={"clientKey": api_key, **data},
        )
        if not response.ok:
            raise CaptchaError("provider_http_error")
        result = await response.json()
        if not isinstance(result, dict) or result.get("errorId") != 0:
            raise CaptchaError("provider_error")
        return result

    result = await post("createTask", {"task": task})
    task_id = result.get("taskId")
    while True:
        if result.get("status") == "ready":
            solution = result.get("solution") or {}
            token = solution.get("gRecaptchaResponse") if isinstance(solution, dict) else None
            if not isinstance(token, str) or not token.strip():
                raise CaptchaError("missing_token")
            return token
        if result.get("status") not in (None, "idle", "processing") or not task_id:
            raise CaptchaError("invalid_task")
        await asyncio.sleep(2)
        result = await post("getTaskResult", {"taskId": task_id})


async def solve(api_key: str, task: dict, timeout: float) -> str:
    try:
        async with asyncio.timeout(timeout):
            async with async_playwright() as playwright:
                # Separate request context: no portal cookies or identity fields.
                request = await playwright.request.new_context(timeout=15000)
                try:
                    return await solve_with_request(request, api_key, task)
                finally:
                    await request.dispose()
    except TimeoutError as exc:
        raise CaptchaError("timeout") from exc
    except (PlaywrightError, ValueError) as exc:
        raise CaptchaError("provider_unavailable") from exc


async def solve_page(page, api_key: str, timeout: float) -> None:
    task = await page.evaluate(r"""() => {
        const frame = [...document.querySelectorAll('iframe[src*="recaptcha"]')]
            .find(el => el.src.includes('/api2/anchor') || el.src.includes('/enterprise/anchor'));
        const widget = document.querySelector('.g-recaptcha[data-sitekey]');
        const url = frame ? new URL(frame.src) : null;
        const key = widget?.dataset.sitekey || url?.searchParams.get('k');
        if (!key) return null;
        const enterprise = url?.pathname.includes('/enterprise/');
        const task = {
            type: enterprise ? 'ReCaptchaV2EnterpriseTaskProxyLess' : 'ReCaptchaV2TaskProxyLess',
            // Strip query parameters so identity fields cannot reach the provider.
            websiteURL: location.origin + location.pathname,
            websiteKey: key,
            isInvisible: widget?.dataset.size === 'invisible' || url?.searchParams.get('size') === 'invisible'
        };
        const s = widget?.dataset.s || url?.searchParams.get('s');
        if (s) {
            if (enterprise) task.enterprisePayload = {s};
            else task.recaptchaDataSValue = s;
        }
        const action = url?.searchParams.get('sa');
        if (action) task.pageAction = action;
        if (url?.hostname.endsWith('recaptcha.net')) task.apiDomain = 'www.recaptcha.net';
        return task;
    }""")
    if not task:
        raise CaptchaError("unsupported_captcha")
    token = await solve(api_key, task, timeout)
    applied = await page.evaluate("""token => {
        const fields = document.querySelectorAll('[name="g-recaptcha-response"]');
        for (const field of fields) {
            field.value = token;
            field.dispatchEvent(new Event('input', {bubbles: true}));
            field.dispatchEvent(new Event('change', {bubbles: true}));
        }
        const callbacks = new Set();
        for (const el of document.querySelectorAll('[data-callback]')) {
            const fn = el.dataset.callback.split('.').reduce((obj, key) => obj?.[key], window);
            if (typeof fn === 'function') callbacks.add(fn);
        }
        const seen = new WeakSet();
        function visit(obj, depth) {
            if (!obj || typeof obj !== 'object' || depth > 6 || seen.has(obj) || obj instanceof Element) return;
            seen.add(obj);
            for (const key of Object.keys(obj)) {
                const value = obj[key];
                if (key === 'callback' && typeof value === 'function') callbacks.add(value);
                else if (typeof value === 'object') visit(value, depth + 1);
            }
        }
        visit(window.___grecaptcha_cfg?.clients, 0);
        for (const fn of callbacks) fn(token);
        return fields.length > 0 || callbacks.size > 0;
    }""", token)
    if not applied:
        raise CaptchaError("token_not_applied")
