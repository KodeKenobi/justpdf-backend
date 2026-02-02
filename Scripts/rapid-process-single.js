#!/usr/bin/env node
/**
 * Rapid Process Single Company
 * Called by Python backend to process one company with form submission
 * Usage: node rapid-process-single.js <url> <company_name> <message> [email] [phone] [contact_person]
 */

const { chromium } = require('playwright');

class RapidProcessor {
  constructor(url, senderProfileJson) {
    this.url = url;
    this.senderProfile = {};
    this.prefixWasSelected = false;

    // Load Profile
    if (senderProfileJson) {
      try {
        let jsonStr = senderProfileJson;
        const fs = require('fs');
        const path = require('path');
        if (jsonStr.endsWith('.json') && fs.existsSync(jsonStr)) {
          jsonStr = fs.readFileSync(jsonStr, 'utf8');
        } else if (jsonStr.startsWith('{')) {
          // Direct JSON
        } else {
          const possiblePath = path.resolve(jsonStr);
          if (fs.existsSync(possiblePath) && !fs.lstatSync(possiblePath).isDirectory()) {
             jsonStr = fs.readFileSync(possiblePath, 'utf8');
          }
        }
        this.senderProfile = typeof jsonStr === 'string' ? JSON.parse(jsonStr) : jsonStr;
      } catch (e) {
        this.log('WARNING', 'Profile Error', `Failed to parse: ${e.message}`);
      }
    }

    // Dial Codes for Deduplication
    this.countryDialCodes = {
      'united kingdom': '44', 'south africa': '27', 'united states': '1', 'canada': '1',
      'australia': '61', 'germany': '49', 'france': '33', 'india': '91', 'china': '86'
    };

    // Fallbacks
    this.companyName = this.senderProfile.sender_company || 'Business';
    this.message = this.senderProfile.message || '';
    this.email = this.senderProfile.sender_email || 'contact@business.com';
    this.phone = this.senderProfile.sender_phone || '';
    this.contactPerson = this.senderProfile.sender_name || 'Contact';
    this.subject = this.senderProfile.subject || 'Inquiry';

    this.log('INFO', 'Config', `Target: ${this.url} | Sender: ${this.contactPerson}`);
  }

  log(level, action, message) {
    console.error(`[${level}] ${action}: ${message}`);
  }

  async findContactLink(page) {
    try {
      const contactLinks = await page.$$eval('a', (links) => {
        return links
          .filter(link => {
            const href = (link.getAttribute('href') || '').toLowerCase();
            const text = (link.textContent || '').toLowerCase().trim();
            return (href.includes('contact') || text.includes('contact') || text.includes('get in touch')) &&
                   link.offsetParent !== null;
          })
          .map(link => link.href)
          .filter(href => href && href.startsWith('http'));
      });
      
      return contactLinks[0] || null;
    } catch (e) {
      this.log('ERROR', 'Contact Link Search', e.message);
      return null;
    }
  }

  async handleCookieModal(page) {
    let dismissedCount = 0;
    try {
      const cookieButton = await page.getByRole('button', { name: /accept|agree|close|dismiss/i }).first();
      if (await cookieButton.isVisible({ timeout: 1500 })) {
        await cookieButton.click();
        dismissedCount++;
        this.log('INFO', 'Modal Dismiss', 'Clicked via Role');
        await page.waitForTimeout(500);
      }
    } catch (e) { }

    const selectors = [
      'button:has-text("Accept")', 'button:has-text("Accept All")', 'button:has-text("I Accept")',
      'button:has-text("Agree")', '#accept-cookies', '#acceptCookies', '.cookie-accept',
      'button:has-text("Reject")', 'button:has-text("Reject All")', 'button:has-text("Decline")',
      'button:has-text("Close")', '[aria-label*="Close" i]', '[aria-label*="Reject" i]',
      '.cookie-close', '.cookie-dismiss', '[class*="cookie" i] button[class*="close" i]',
      'div[class*="close" i]', 'span[class*="close" i]', 'button[class*="close" i]',
      '.hb-close-button', '.hubspot-messages-iframe-container .close-button',
      '[class*="chatbot" i] [class*="close" i]', '[id*="chatbot" i] [class*="close" i]'
    ];

    for (const selector of selectors) {
      try {
        const elements = page.locator(selector);
        const count = await elements.count();
        if (count > 0) {
          const el = elements.first();
          if (await el.isVisible({ timeout: 500 })) {
            await el.click();
            dismissedCount++;
            this.log('INFO', 'Modal Dismiss', `Clicked: ${selector}`);
            await page.waitForTimeout(300);
          }
        }
      } catch (e) { }
    }

    // Check iframes for close buttons (e.g. Chatbots)
    for (const frame of page.frames()) {
      try {
        const closeBtn = await frame.$('.close-button, [aria-label*="Close" i], button:has-text("Dismiss")');
        if (closeBtn && await closeBtn.isVisible({ timeout: 500 })) {
          await closeBtn.click();
          dismissedCount++;
        }
      } catch (e) { }
    }

    return dismissedCount > 0;
  }

  async detectCaptcha(form) {
    try {
      const captchaIndicators = [
        '.g-recaptcha', '#recaptcha', 'iframe[src*="recaptcha"]', 'div[class*="captcha" i]'
      ];
      for (const selector of captchaIndicators) {
        if (await form.$(selector)) return true;
      }
      return false;
    } catch (e) { return false; }
  }

  async handleSelectField(select, fieldText) {
    try {
      const options = await select.$$eval('option', (opts) => {
        return opts.map(opt => ({
          text: (opt.textContent || '').toLowerCase().trim(),
          value: opt.getAttribute('value') || ''
        })).filter(o => o.value !== '' && o.text.length > 0);
      });

      if (options.length === 0) return false;

      const profile = this.senderProfile;
      const country = (profile.sender_country || '').toLowerCase();
      const dialCode = this.countryDialCodes[country];

      let isCountryOrPrefix = fieldText.includes('country') || fieldText.includes('nation') || fieldText.includes('prefix') || fieldText.includes('dial') || fieldText.includes('phone') || fieldText.includes('location');
      
      if (!isCountryOrPrefix) {
        const hasDialCodes = options.some(o => o.text.includes('+') && /\d+/.test(o.text));
        if (hasDialCodes) isCountryOrPrefix = true;
      }

      if (isCountryOrPrefix) {
        for (const opt of options) {
          const countryMatch = country && (opt.text.includes(country) || country.includes(opt.text));
          const dialMatch = dialCode && (opt.text.includes(`+${dialCode}`) || opt.value === dialCode || opt.value === `+${dialCode}`);
          
          if (countryMatch || dialMatch) {
            await select.selectOption(opt.value);
            this.log('INFO', 'Field Fill', `Matched 'Select': ${opt.text}`);
            return true;
          }
        }
      }
      return false;
    } catch (e) {
      return false;
    }
  }

  async fillAndSubmitForm(mainPage, frame, form) {
    try {
      const elements = await form.$$('input:not([type="hidden"]), textarea, select');
      
      let discoveryList = `Found ${elements.length} form fields:\n`;
      for (let i = 0; i < elements.length; i++) {
        const details = await elements[i].evaluate(el => {
          const tag = el.tagName.toLowerCase();
          const type = el.getAttribute('type') || (tag === 'select' ? 'select' : 'text');
          const name = el.getAttribute('name') || el.getAttribute('id') || 'unnamed';
          let label = '';
          const lEl = document.querySelector(`label[for="${el.id}"]`) || el.closest('label');
          if (lEl) label = lEl.textContent.trim().replace(/\s+/g, ' ');
          return `[${tag}:${type}] Name: '${name}', Label: "${label}"`;
        });
        discoveryList += `[INFO] Field ${i+1}. ${details}\n`;
      }
      console.error(`[INFO] Discovery: ${discoveryList}`);

      if (await this.detectCaptcha(form)) {
        return { success: false, method: 'form_with_captcha', error: 'Form has CAPTCHA' };
      }

      let filledCount = 0;
      let emailFilled = false, messageFilled = false, nameFilled = false, companyFilled = false;
      const profile = this.senderProfile;

      // PASS 1: Selects
      const allSelects = await frame.$$('select');
      for (const sel of allSelects) {
        try {
          const nameAttr = (await sel.getAttribute('name') || '').toLowerCase();
          const idAttr = (await sel.getAttribute('id') || '').toLowerCase();
          const labelText = await sel.evaluate(el => {
            let label = document.querySelector(`label[for="${el.id}"]`) || el.closest('label');
            return label ? label.textContent.toLowerCase() : '';
          });
          const fieldText = `${nameAttr} ${idAttr} ${labelText}`.toLowerCase();

          if (fieldText.includes('country') || fieldText.includes('nation') || fieldText.includes('prefix') || fieldText.includes('dial') || fieldText.includes('phone') || fieldText.includes('ext')) {
            const filled = await this.handleSelectField(sel, fieldText);
            if (filled) filledCount++;
          }
        } catch (e) { }
      }

      // PASS 2: Inputs
      const checkboxGroups = {};
      for (const el of elements) {
        try {
          const tagName = await el.evaluate(el => el.tagName.toLowerCase());
          if (tagName === 'select') continue;

          const type = await el.getAttribute('type') || 'text';
          const nameAttr = (await el.getAttribute('name') || '');
          const idAttr = (await el.getAttribute('id') || '').toLowerCase();
          const placeholder = (await el.getAttribute('placeholder') || '').toLowerCase();
          const labelText = await el.evaluate(el => {
            let label = document.querySelector(`label[for="${el.id}"]`) || el.closest('label');
            return label ? label.textContent.toLowerCase() : '';
          });
          const fieldText = `${nameAttr} ${placeholder} ${idAttr} ${labelText}`.toLowerCase();

          if (['checkbox', 'radio'].includes(type)) {
            const groupName = nameAttr || idAttr || labelText;
            if (!checkboxGroups[groupName]) checkboxGroups[groupName] = [];
            checkboxGroups[groupName].push({ el, labelText, type });
            continue;
          }

          if (type === 'submit' || type === 'button') continue;

          // Email
          if (!emailFilled && (type === 'email' || fieldText.includes('email'))) {
            await el.fill(profile.sender_email || this.email);
            emailFilled = true; filledCount++; 
            this.log('INFO', 'Field Fill', 'Matched \'Email\'');
            continue;
          }

          // Names
          const isGenericName = fieldText.includes('name') && !['first','last','company','business'].some(x => fieldText.includes(x));
          if (fieldText.includes('first') || fieldText.includes('fname')) {
            await el.fill(profile.sender_first_name || this.contactPerson.split(' ')[0]);
            filledCount++; this.log('INFO', 'Field Fill', 'Matched \'First Name\''); continue;
          }
          if (fieldText.includes('last') || fieldText.includes('lname')) {
            await el.fill(profile.sender_last_name || this.contactPerson.split(' ').slice(1).join(' '));
            filledCount++; this.log('INFO', 'Field Fill', 'Matched \'Last Name\''); continue;
          }
          if (!nameFilled && isGenericName) {
            await el.fill(profile.sender_name || this.contactPerson);
            nameFilled = true; filledCount++; this.log('INFO', 'Field Fill', 'Matched \'Full Name\''); continue;
          }

          // Company
          if (!companyFilled && (fieldText.includes('company') || fieldText.includes('business'))) {
            await el.fill(profile.sender_company || this.companyName);
            companyFilled = true; filledCount++; this.log('INFO', 'Field Fill', 'Matched \'Company\''); continue;
          }

          // Phone
          if (type === 'tel' || fieldText.includes('phone')) {
            let val = profile.sender_phone || this.phone;
            val = val.replace(/[^\d+]/g, '');
            const dialCode = this.countryDialCodes[(profile.sender_country || '').toLowerCase()];
            if (dialCode && (val.startsWith(`+${dialCode}`) || val.startsWith(dialCode))) {
              const pre = val.startsWith('+') ? `+${dialCode}` : dialCode;
              if (val.slice(pre.length).length >= 6) val = val.slice(pre.length);
            }
            await el.fill(val.replace(/^[\s+]+/, ''));
            filledCount++; this.log('INFO', 'Field Fill', 'Matched \'Phone\''); continue;
          }

          // Message
          if (tagName === 'textarea' && !messageFilled && (fieldText.includes('message') || fieldText.includes('comment') || fieldText.includes('enquiry'))) {
            await el.fill(profile.message || this.message);
            messageFilled = true; filledCount++; this.log('INFO', 'Field Fill', 'Matched \'Message\''); continue;
          }

        } catch (e) { }
      }

      // PASS 3: Checkboxes
      for (const [name, items] of Object.entries(checkboxGroups)) {
        try {
          const context = `${this.subject} ${this.message}`.toLowerCase();
          for (const item of items) {
            if (item.labelText && (context.includes(item.labelText.toLowerCase()) || item.labelText.toLowerCase().includes('sales'))) {
              await item.el.check();
              this.log('INFO', 'Field Fill', `Matched 'Checkbox': ${item.labelText}`);
              filledCount++;
              break;
            }
          }
        } catch (e) { }
      }

      if (!emailFilled || !messageFilled) {
        return { success: false, method: 'incomplete_form', error: 'Missing req fields', fields_filled: filledCount };
      }

      // Final cookie dismissal before screenshot
      await this.handleCookieModal(mainPage);

      const screenshotPath = `screenshots/before-submit-${Date.now()}.png`;
      await mainPage.screenshot({ path: screenshotPath });

      this.log('SUCCESS', 'Finished', `--- Successfully filled ${filledCount} fields ---`);
      return { success: true, method: 'form_filled_ready', fields_filled: filledCount, screenshot_url: screenshotPath };
    } catch (e) {
      return { success: false, method: 'error', error: e.message };
    }
  }

  async process() {
    const browser = await chromium.launch({
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const context = await browser.newContext({
      viewport: { width: 1920, height: 1080 },
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    });

    const page = await context.newPage();

    try {
      this.log('INFO', 'Navigation', `Visiting: ${this.url}`);
      await page.goto(this.url, { waitUntil: 'domcontentloaded', timeout: 60000 });
      await this.handleCookieModal(page);
      
      this.log('INFO', 'Navigation', 'Wait 7s for dynamic renderings...');
      await page.waitForTimeout(7000); 

      const findForms = async (p) => {
        let allForms = [];
        for (const frame of p.frames()) {
          try {
            const inputs = await frame.$$('input:not([type="hidden"]), textarea, select');
            if (inputs.length >= 3) {
              const form = await frame.$('form') || await frame.$('body');
              if (form) allForms.push({ form, frame, inputsCount: inputs.length });
            }
          } catch (e) { }
        }
        return allForms;
      };

      const executeFill = async (wrappers) => {
        wrappers.sort((a, b) => b.inputsCount - a.inputsCount);
        for (const wrapper of wrappers) {
          this.log('INFO', 'Form Match', `Evaluating Form (${wrapper.inputsCount} fields)`);
          const res = await this.fillAndSubmitForm(page, wrapper.frame, wrapper.form);
          if (res.success) return res;
        }
        return null;
      };

      // Try discovery multiple times
      let forms = [];
      for (let i = 0; i < 3; i++) {
        forms = await findForms(page);
        if (forms.length > 0) break;
        this.log('INFO', 'Discovery', `No forms found, retrying (${i+1}/3)...`);
        await page.waitForTimeout(3000);
      }

      if (forms.length > 0) {
        let result = await executeFill(forms);
        if (result) return result;
      }

      // Fallback Strategy: Discovery via Homepage if initial URL failed to provide a form
      const urlObj = new URL(this.url);
      const homepage = `${urlObj.protocol}//${urlObj.hostname}`;
      
      this.log('INFO', 'Navigation', `No form on landing page. Searching homepage: ${homepage}`);
      await page.goto(homepage, { waitUntil: 'domcontentloaded' });
      await this.handleCookieModal(page);
      await page.waitForTimeout(3000);
      
      const contactUrl = await this.findContactLink(page);
      if (contactUrl) {
        this.log('INFO', 'Navigation', `Found contact link: ${contactUrl}`);
        await page.goto(contactUrl, { waitUntil: 'domcontentloaded' });
        await this.handleCookieModal(page);
        await page.waitForTimeout(7000);
        
        forms = await findForms(page);
        if (forms.length === 0) {
          this.log('INFO', 'Discovery', 'Retrying frame check on contact page...');
          await page.waitForTimeout(3000);
          forms = await findForms(page);
        }
        
        let finalRes = await executeFill(forms);
        if (finalRes) return finalRes;
      }

      const emails = await page.$$eval('a[href^="mailto:"]', l => l.map(x => x.href.replace('mailto:', '')));
      if (emails.length > 0) {
        this.log('SUCCESS', 'Fallback', `Found email: ${emails[0]}`);
        return { success: true, method: 'email_found', contact_info: { emails } };
      }

      const screenshot = `screenshots/not-found-${Date.now()}.png`;
      await page.screenshot({ path: screenshot, fullPage: true });
      return { success: false, method: 'not_found', error: 'No form found', screenshot_url: screenshot };

    } catch (e) {
      this.log('ERROR', 'Process', e.message);
      return { success: false, method: 'error', error: e.message };
    } finally {
      if (browser) await browser.close();
    }
  }
}

// Main execution
(async () => {
  const args = process.argv.slice(2);
  
  if (args.length < 2) {
    console.error('Usage: node rapid-process-single.js <url> <senderProfileJsonOrPath>');
    process.exit(1);
  }

  const [url, profileJson] = args;
  const processor = new RapidProcessor(url, profileJson);
  const result = await processor.process();

  console.log(JSON.stringify(result, null, 2));
  process.exit(result.success ? 0 : 1);
})();
