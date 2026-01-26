import csv
import asyncio
from playwright.async_api import async_playwright


CONTACT_FORM_SELECTORS = [
    'form[id*="contact" i]',
    'form[class*="contact" i]',
    'form[name*="contact" i]',
    'form[action*="contact" i]',
    'form:has(input[type="email"])',
    'form:has(input[name*="email" i])',
    'form:has(input[name*="name" i])',
    'form:has(textarea)',
    'form:has(button[type="submit"])',
    '[id*="contact-form" i]',
    '[class*="contact-form" i]',
    '[id*="contactForm" i]',
    '[class*="contactForm" i]',
    'form:has(label:has-text("email" i))',
    'form:has(label:has-text("name" i))',
    'form',
    'form input[type="email"]',
    'form input[type="text"]',
    'form textarea',
    'form button[type="submit"]',
    'form button:has-text("submit" i)',
    'form button:has-text("send" i)',
]

CONTACT_SECTION_SELECTORS = [
    'section[id*="contact" i]',
    'section[class*="contact" i]',
    'div[id*="contact" i]',
    'div[class*="contact" i]',
    'main[id*="contact" i]',
    'main[class*="contact" i]',
    'article[id*="contact" i]',
    'article[class*="contact" i]',
    '[id*="contact" i]',
    '[class*="contact" i]',
    'h1:has-text("contact" i)',
    'h2:has-text("contact" i)',
    'h3:has-text("contact" i)',
    'h4:has-text("contact" i)',
    '*:has-text("get in touch" i)',
    '*:has-text("contact us" i)',
    '*:has-text("reach out" i)',
]

CONTACT_LINK_SELECTORS = [
    'a[href*="contact" i]',
    'nav a:has-text("contact" i)',
    'a:has-text("contact" i)',
    'a:has-text("get in touch" i)',
    'a:has-text("reach out" i)',
    'a:has-text("contact us" i)',
    '[href*="/contact"]',
    '[href*="contact.html"]',
    '[href*="contact.php"]',
]

COOKIE_SELECTORS = [
    'button:has-text("Accept" i)',
    'button:has-text("Accept All" i)',
    'button:has-text("Accept Cookies" i)',
    'button:has-text("I Accept" i)',
    'button:has-text("Agree" i)',
    'button:has-text("OK" i)',
    'button:has-text("Got it" i)',
    'button:has-text("Allow" i)',
    'button:has-text("Allow All" i)',
    'button:has-text("Consent" i)',
    'button:has-text("Continue" i)',
    'button:has-text("Close" i)',
    '#accept-cookies',
    '#acceptAllCookies',
    '#cookieAccept',
    '#cookie-accept',
    '#acceptCookie',
    '#cookie-consent-accept',
    '.cookie-accept',
    '.accept-cookies',
    '.cookie-consent-accept',
    '.cookie-banner-accept',
    '[data-cookie-accept]',
    '[data-accept-cookies]',
    '[id*="cookie" i] button',
    '[class*="cookie" i] button',
    '[id*="consent" i] button',
    '[class*="consent" i] button',
    '[id*="gdpr" i] button',
    '[class*="gdpr" i] button',
]


async def handle_cookie_modal(page):
    await page.wait_for_timeout(2000)
    for selector in COOKIE_SELECTORS:
        try:
            button = page.locator(selector).first
            if await button.is_visible(timeout=1000):
                await button.click()
                await page.wait_for_timeout(500)
                return True
        except:
            continue

    cookie_elements = await page.locator(
        '[id*="cookie" i], [class*="cookie" i], [id*="consent" i], [class*="consent" i]'
    ).all()

    for element in cookie_elements:
        try:
            button = element.locator("button").first
            if await button.is_visible(timeout=500):
                await button.click()
                await page.wait_for_timeout(500)
                return True
        except:
            continue

    return False


async def extract_form_details(page, form_element=None):
    details = {"fields": [], "textareas": [], "selects": [], "buttons": [], "labels": []}

    try:
        form = form_element or page.locator("form").first

        inputs = await form.locator("input").all()
        for input_el in inputs:
            type_attr = await input_el.get_attribute("type") or "text"
            name = await input_el.get_attribute("name") or ""
            id_attr = await input_el.get_attribute("id") or ""
            placeholder = await input_el.get_attribute("placeholder") or ""
            required = await input_el.get_attribute("required") is not None

            label_text = ""
            if id_attr:
                label = page.locator(f'label[for="{id_attr}"]').first
                if await label.count() > 0:
                    label_text = (await label.text_content() or "").strip()

            if not label_text:
                parent_label = input_el.locator("xpath=ancestor::label").first
                if await parent_label.count() > 0:
                    label_text = (await parent_label.text_content() or "").strip()

            details["fields"].append(
                {
                    "type": type_attr,
                    "name": name,
                    "id": id_attr,
                    "placeholder": placeholder,
                    "required": required,
                    "label": label_text,
                }
            )

        textareas = await form.locator("textarea").all()
        for textarea in textareas:
            name = await textarea.get_attribute("name") or ""
            id_attr = await textarea.get_attribute("id") or ""
            placeholder = await textarea.get_attribute("placeholder") or ""
            required = await textarea.get_attribute("required") is not None
            rows = await textarea.get_attribute("rows") or ""

            label_text = ""
            if id_attr:
                label = page.locator(f'label[for="{id_attr}"]').first
                if await label.count() > 0:
                    label_text = (await label.text_content() or "").strip()

            if not label_text:
                parent_label = textarea.locator("xpath=ancestor::label").first
                if await parent_label.count() > 0:
                    label_text = (await parent_label.text_content() or "").strip()

            details["textareas"].append(
                {
                    "name": name,
                    "id": id_attr,
                    "placeholder": placeholder,
                    "required": required,
                    "rows": rows,
                    "label": label_text,
                }
            )

        selects = await form.locator("select").all()
        for select in selects:
            name = await select.get_attribute("name") or ""
            id_attr = await select.get_attribute("id") or ""
            required = await select.get_attribute("required") is not None

            options = []
            option_elements = await select.locator("option").all()
            for option in option_elements:
                options.append(
                    {
                        "value": await option.get_attribute("value") or "",
                        "text": (await option.text_content() or "").strip(),
                    }
                )

            label_text = ""
            if id_attr:
                label = page.locator(f'label[for="{id_attr}"]').first
                if await label.count() > 0:
                    label_text = (await label.text_content() or "").strip()

            details["selects"].append(
                {"name": name, "id": id_attr, "required": required, "options": options, "label": label_text}
            )

        buttons = await form.locator("button, input[type='submit'], input[type='button']").all()
        for button in buttons:
            type_attr = await button.get_attribute("type") or "button"
            text = (await button.text_content() or "").strip()
            value = await button.get_attribute("value") or ""
            id_attr = await button.get_attribute("id") or ""
            class_name = await button.get_attribute("class") or ""
            details["buttons"].append({"type": type_attr, "text": text or value, "id": id_attr, "className": class_name})

    except:
        pass

    return details


async def find_contact_form(page):
    found = []

    try:
        form_count = await page.locator("form").count()
        if form_count > 0:
            found.append("form [ANY FORM FOUND]")
            print(f"      ✓ Found {form_count} form(s) on page")
    except:
        pass

    try:
        forms_with_email = await page.locator("form:has(input[type='email'])").count()
        if forms_with_email > 0:
            found.append("form:has(input[type='email'])")
    except:
        pass

    try:
        forms_with_textarea = await page.locator("form:has(textarea)").count()
        if forms_with_textarea > 0:
            found.append("form:has(textarea)")
    except:
        pass

    try:
        forms_with_submit = await page.locator("form:has(button[type='submit']), form:has(input[type='submit'])").count()
        if forms_with_submit > 0:
            found.append("form:has(button[type='submit'])")
    except:
        pass

    for selector in CONTACT_FORM_SELECTORS:
        try:
            count = await page.locator(selector).count()
            if count > 0 and selector not in found:
                found.append(selector)
        except:
            pass

    return found


async def find_contact_section(page):
    found = []
    for selector in CONTACT_SECTION_SELECTORS:
        try:
            elements = await page.locator(selector).all()
            if elements:
                found.append(selector)
        except:
            pass
    return found


async def find_contact_links(page):
    found = []
    links = []

    for selector in CONTACT_LINK_SELECTORS:
        try:
            elements = await page.locator(selector).all()
            if elements:
                found.append(selector)
                for element in elements:
                    href = await element.get_attribute("href")
                    if href:
                        links.append(href)
        except:
            pass

    return {"selectors": found, "links": links}


async def test_website(url):
    result = {
        "url": url,
        "contactFormFound": False,
        "contactSectionFound": False,
        "contactLinkFound": False,
        "contactPageFound": False,
        "foundSelectors": [],
        "pageTitle": "",
        "pageContent": "",
        "errors": [],
    }

    browser = await async_playwright().start()
    chromium = browser.chromium
    browser = await chromium.launch(headless=False, args=["--no-sandbox", "--disable-setuid-sandbox"])
    page = await browser.new_page()

    try:
        print(f"\n🌐 Testing: {url}")
        await page.set_viewport_size({"width": 1920, "height": 1080})

        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        result["pageTitle"] = await page.title()

        cookie_handled = await handle_cookie_modal(page)
        print(f"🍪 Cookie modal handled: {cookie_handled}")

        await page.wait_for_load_state("networkidle", timeout=10000).catch(lambda e: None)

        body_text = await page.text_content("body")
        result["pageContent"] = (body_text or "")[:500]

        contact_forms = await find_contact_form(page)
        result["contactFormFound"] = len(contact_forms) > 0
        if contact_forms:
            result["foundSelectors"].extend(contact_forms)
            print(f"✅ Contact forms found: {len(contact_forms)}")
            for sel in contact_forms:
                print(f"   - {sel}")

        contact_sections = await find_contact_section(page)
        result["contactSectionFound"] = len(contact_sections) > 0
        if contact_sections:
            result["foundSelectors"].extend(contact_sections)
            print(f"✅ Contact sections found: {len(contact_sections)}")
            for sel in contact_sections:
                print(f"   - {sel}")

        links_data = await find_contact_links(page)
        contact_link_selectors = links_data["selectors"]
        contact_links = links_data["links"]

        result["contactLinkFound"] = len(contact_link_selectors) > 0
        if contact_link_selectors:
            result["foundSelectors"].extend(contact_link_selectors)
            print(f"✅ Contact links found: {len(contact_link_selectors)}")
            for sel in contact_link_selectors:
                print(f"   - {sel}")
            print(f"   Links: {', '.join(contact_links)}")

        if contact_links:
            unique_contact_urls = list(
                dict.fromkeys(
                    [
                        (link if link.startswith("http") else f"{url.rstrip('/')}/{link.lstrip('/')}")
                        for link in contact_links
                    ]
                )
            )

            for contact_url in unique_contact_urls:
                print(f"\n🔍 Navigating to contact page: {contact_url}")

                try:
                    await page.goto(contact_url, wait_until="domcontentloaded", timeout=20000)
                    await handle_cookie_modal(page)

                    print("   ⏳ Waiting for page to load...")
                    await page.wait_for_load_state("networkidle", timeout=15000).catch(lambda e: None)
                    await page.wait_for_timeout(5000)

                    print("   ⏳ Waiting for form elements to load...")
                    await page.wait_for_selector(
                        "form, input[type='email'], textarea, button[type='submit']",
                        timeout=10000,
                    ).catch(lambda e: None)

                    await page.wait_for_timeout(3000)

                    all_forms = await page.locator("form").count()
                    all_inputs = await page.locator("input").count()
                    all_textareas = await page.locator("textarea").count()
                    print(f"   📊 Page has: {all_forms} form(s), {all_inputs} input(s), {all_textareas} textarea(s)")

                    contact_page_forms = []
                    contact_page_sections = await find_contact_section(page)

                    if all_forms > 0:
                        contact_page_forms.append("form [FOUND ON CONTACT PAGE]")
                        print(f"   ✅ Found {all_forms} form(s) - treating as contact form!")
                    else:
                        contact_page_forms = await find_contact_form(page)

                    if not contact_page_forms and not contact_page_sections:
                        print("   ⏳ No forms found yet, waiting longer...")
                        await page.wait_for_timeout(5000)

                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await page.wait_for_timeout(2000)
                        await page.evaluate("window.scrollTo(0, 0)")
                        await page.wait_for_timeout(2000)

                        contact_page_forms = await find_contact_form(page)
                        contact_page_sections = await find_contact_section(page)

                        if not contact_page_forms and all_forms > 0:
                            print("   🔍 Found forms but selectors didn't match, trying generic detection...")
                            forms_with_email = await page.locator("form:has(input[type='email'])").count()
                            if forms_with_email > 0:
                                contact_page_forms.append("form:has(input[type='email']) [GENERIC]")
                                print("   ✅ Found form with email input using generic selector!")

                            forms_with_textarea = await page.locator("form:has(textarea)").count()
                            if forms_with_textarea > 0 and not contact_page_forms:
                                contact_page_forms.append("form:has(textarea) [GENERIC]")
                                print("   ✅ Found form with textarea using generic selector!")

                            if not contact_page_forms and all_forms > 0:
                                contact_page_forms.append("form [GENERIC - ANY FORM ON CONTACT PAGE]")
                                print("   ✅ Found forms on contact page - assuming contact form!")

                    iframes = await page.locator("iframe").all()
                    if iframes and not contact_page_forms:
                        print(f"   🔍 Found {len(iframes)} iframe(s), checking inside...")
                        for iframe in iframes[:3]:
                            try:
                                frame = await iframe.content_frame()
                                if frame:
                                    iframe_forms = await frame.locator("form").count()
                                    if iframe_forms > 0:
                                        contact_page_forms.append("form [IN IFRAME]")
                                        print(f"   ✅ Found {iframe_forms} form(s) in iframe!")

                                        print("\n📋 Extracting form details from iframe...")
                                        iframe_form_details = await extract_form_details(frame)
                                        print("\n📝 IFRAME FORM FIELDS:")
                                        print(iframe_form_details)

                                        break
                            except:
                                pass

                    if contact_page_forms:
                        result["contactPageFound"] = True
                        result["contactFormFound"] = True
                        result["foundSelectors"].extend([f"[CONTACT PAGE] {f}" for f in contact_page_forms])
                        print("✅ Contact page has forms!")
                        for sel in contact_page_forms:
                            print(f"   - {sel}")

                        print("\n📋 Extracting form details...")
                        form_details = await extract_form_details(page)
                        print("\n📝 FORM FIELDS:")
                        print(form_details)

                    if contact_page_sections:
                        result["contactPageFound"] = True
                        result["contactSectionFound"] = True
                        result["foundSelectors"].extend([f"[CONTACT PAGE] {s}" for s in contact_page_sections])
                        print("✅ Contact page has sections!")
                        for sel in contact_page_sections:
                            print(f"   - {sel}")

                    if contact_page_forms or contact_page_sections:
                        break

                    contact_buttons = await page.locator(
                        'button:has-text("contact" i), button:has-text("get in touch" i), button:has-text("reach out" i)'
                    ).all()

                    if contact_buttons:
                        print(f"\n🔘 Found {len(contact_buttons)} contact-related buttons, trying to click...")
                        for button in contact_buttons[:3]:
                            try:
                                if await button.is_visible(timeout=1000):
                                    await button.click()
                                    await page.wait_for_timeout(2000)

                                    popup_forms = await find_contact_form(page)
                                    if popup_forms:
                                        result["contactFormFound"] = True
                                        result["foundSelectors"].extend([f"[BUTTON CLICKED] {f}" for f in popup_forms])
                                        print("✅ Form appeared after clicking button!")
                                        for sel in popup_forms:
                                            print(f"   - {sel}")
                                        break
                            except:
                                pass

                except Exception as e:
                    result["errors"].append(f"Failed to navigate to contact page {contact_url}: {str(e)}")
                    print(f"❌ Could not navigate to contact page: {str(e)}")

        if not result["contactFormFound"] and not result["contactSectionFound"]:
            print("\n📋 All links containing 'contact':")
            all_links = await page.locator('a[href*="contact" i]').all()
            for link in all_links:
                href = await link.get_attribute("href")
                text = await link.text_content()
                print(f"   - {text.strip() if text else ''}: {href}")

            print("\n📋 All elements with 'contact' in id/class:")
            contact_elements = await page.locator('[id*="contact" i], [class*="contact" i]').all()
            for element in contact_elements[:10]:
                id_attr = await element.get_attribute("id")
                class_name = await element.get_attribute("class")
                tag_name = await element.evaluate("el => el.tagName")
                class_first = class_name.split(" ")[0] if class_name else ""
                print(f"   - {tag_name}{('#'+id_attr) if id_attr else ''}{('.'+class_first) if class_first else ''}")

    except Exception as error:
        result["errors"].append(str(error))
        print(f"❌ Error: {str(error)}")

    finally:
        await page.close()
        await browser.close()

    return result


async def main():
    url = "https://2020innovation.com"
    print("🚀 Starting single site contact form test...\n")
    print(f"Testing: {url}\n")

    result = await test_website(url)

    print("\n" + "=" * 60)
    print("📊 TEST RESULTS")
    print("=" * 60)
    print(f"URL: {result['url']}")
    print(f"Page Title: {result['pageTitle']}")
    print(f"Contact Form Found: {'✅' if result['contactFormFound'] else '❌'}")
    print(f"Contact Section Found: {'✅' if result['contactSectionFound'] else '❌'}")
    print(f"Contact Link Found: {'✅' if result['contactLinkFound'] else '❌'}")
    print(f"Contact Page Found: {'✅' if result['contactPageFound'] else '❌'}")
    print(f"Found Selectors: {len(result['foundSelectors'])}")
    for sel in result["foundSelectors"]:
        print(f"   - {sel}")

    if result["errors"]:
        print("\nErrors:")
        for err in result["errors"]:
            print(f"   - {err}")

if __name__ == "__main__":
    asyncio.run(main())
