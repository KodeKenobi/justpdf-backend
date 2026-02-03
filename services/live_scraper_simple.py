    async def find_contact_method_simple(self):
        """
        Simple contact detection using proven methods from logs
        """
        try:
            base_url = self.page.url.rstrip('/')

            # STRATEGY 1: Homepage form check (fastest method from logs)
            await self.send_log('info', 'Contact Detection', 'Checking homepage for forms....')
            forms = await self.page.query_selector_all('form')
            if forms and len(forms) > 0:
                # Analyze form structure (like logs show)
                contact_forms = []
                for form in forms:
                    try:
                        # Get form details
                        inputs = await form.query_selector_all('input, textarea, select')

                        # Count contact-relevant fields
                        contact_score = 0
                        email_fields = 0
                        text_fields = 0

                        for inp in inputs:
                            inp_type = await inp.get_attribute('type') or 'text'
                            name = (await inp.get_attribute('name') or '').lower()
                            placeholder = (await inp.get_attribute('placeholder') or '').lower()

                            # Count contact indicators
                            contact_indicators = ['email', 'name', 'phone', 'message', 'contact', 'subject']
                            if any(indicator in name or indicator in placeholder for indicator in contact_indicators):
                                contact_score += 1

                            if inp_type == 'email':
                                email_fields += 1
                                contact_score += 2
                            elif inp_type in ['text', 'textarea']:
                                text_fields += 1

                        # Consider it a contact form if it has good contact indicators
                        if contact_score >= 2 or (email_fields > 0 and text_fields > 0):
                            contact_forms.append(form)
                            await self.send_log('success', 'Homepage Form Found', f'Form with {len(inputs)} fields, score: {contact_score}')
                    except:
                        continue

                if contact_forms:
                    await self.send_log('success', 'Homepage Form Check', 'Direct form detection on homepage - fastest method')
                    return base_url  # Stay on homepage

            # STRATEGY 2: Contact link search (simple text matching from logs)
            await self.send_log('info', 'Contact Detection', 'Searching for contact links...')
            contact_texts = [
                "contact", "contact us", "get in touch", "reach out", "reach us",
                "talk to us", "connect", "connect with us"
            ]

            for text in contact_texts:
                try:
                    # Search by text content
                    selector = f'a:has-text("{text}")'
                    link = await self.page.query_selector(selector)
                    if link:
                        visible = await link.is_visible()
                        if visible:
                            href = await link.get_attribute('href')
                            if href and not href.startswith('#'):
                                await self.send_log('success', 'Contact Link Search', f'Search links with "{text}" in href or text')
                                # Convert to absolute URL
                                if href.startswith('http'):
                                    return href
                                elif href.startswith('/'):
                                    return base_url + href
                                else:
                                    return base_url + '/' + href
                except:
                    continue

            # STRATEGY 3: Search by href attribute
            for text in contact_texts:
                try:
                    selector = f'a[href*="{text.replace(" ", "")}"]'
                    link = await self.page.query_selector(selector)
                    if link:
                        visible = await link.is_visible()
                        if visible:
                            href = await link.get_attribute('href')
                            if href and not href.startswith('#'):
                                await self.send_log('success', 'Contact Link Search', f'Found href with "{text}" pattern')
                                if href.startswith('http'):
                                    return href
                                elif href.startswith('/'):
                                    return base_url + href
                                else:
                                    return base_url + '/' + href
                except:
                    continue

            # STRATEGY 4: Check common contact URLs directly
            await self.send_log('info', 'Contact Detection', 'Trying direct contact URLs...')
            common_paths = ['/contact', '/contact-us', '/contactus', '/get-in-touch', '/reach-out']

            for path in common_paths:
                try:
                    test_url = base_url + path
                    await self.send_log('info', 'Contact Detection', f'Trying: {test_url}')
                    response = await self.page.goto(test_url, wait_until='domcontentloaded', timeout=5000)
                    if response and response.ok:
                        # Check if this page has a form (Contact page form check from logs)
                        forms = await self.page.query_selector_all('form')
                        if forms and len(forms) > 0:
                            await self.send_log('success', 'Contact Page Form Check', f'Check for form after navigating to contact page')
                            return test_url
                        else:
                            # Go back to homepage
                            await self.page.goto(base_url, wait_until='domcontentloaded')
                except:
                    # Go back to homepage for next try
                    try:
                        await self.page.goto(base_url, wait_until='domcontentloaded')
                    except:
                        pass
                    continue

            await self.send_log('warning', 'Contact Detection', 'No contact forms or pages found')
            return None

        except Exception as e:
            print(f"[Contact Detection] Error: {e}")
            await self.send_log('error', 'Contact Detection', f'Error during contact detection: {str(e)}')
            return None