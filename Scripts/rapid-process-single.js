#!/usr/bin/env node
/**
 * Rapid Process Single Company
 * Called by Python backend to process one company with form submission
 * Usage: node rapid-process-single.js <url> <company_name> <message> [email] [phone] [contact_person]
 */

const { chromium } = require('playwright');

class RapidProcessor {
  constructor(url, companyName, message, email, phone, contactPerson) {
    this.url = url;
    this.companyName = companyName;
    this.message = message;
    this.email = email || 'contact@business.com';
    this.phone = phone || '';
    this.contactPerson = contactPerson || 'Business Contact';
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
    // Try accept buttons first, then reject/close buttons
    const selectors = [
      // Accept buttons
      'button:has-text("Accept")',
      'button:has-text("Accept All")',
      'button:has-text("I Accept")',
      'button:has-text("Agree")',
      '#accept-cookies',
      '#acceptCookies',
      '.cookie-accept',
      '.accept-cookies',
      '[aria-label*="Accept" i]',
      '[aria-label*="Agree" i]',
      // Reject/Close buttons
      'button:has-text("Reject")',
      'button:has-text("Reject All")',
      'button:has-text("Decline")',
      'button:has-text("Close")',
      '[aria-label*="Close" i]',
      '[aria-label*="Reject" i]',
      '.cookie-close',
      '.cookie-dismiss',
      // Generic close buttons on modals
      '[class*="cookie" i] button[class*="close" i]',
      '[class*="consent" i] button[class*="close" i]',
      '[id*="cookie" i] button[class*="close" i]'
    ];

    for (const selector of selectors) {
      try {
        const element = page.locator(selector).first();
        if (await element.isVisible({ timeout: 300 })) {
          await element.click();
          await page.waitForTimeout(200);
          this.log('INFO', 'Cookie Modal', `Dismissed using: ${selector}`);
          return true;
        }
      } catch (e) {
        continue;
      }
    }
    return false;
  }

  async detectCaptcha(form) {
    try {
      const captchaIndicators = [
        'div[class*="captcha" i]',
        'div[class*="recaptcha" i]',
        'iframe[src*="recaptcha"]',
        'iframe[src*="captcha"]',
        '.g-recaptcha',
        '#recaptcha'
      ];

      for (const selector of captchaIndicators) {
        const element = await form.$(selector);
        if (element) {
          this.log('WARNING', 'CAPTCHA', 'CAPTCHA detected in form');
          return true;
        }
      }
      return false;
    } catch (e) {
      return false;
    }
  }

  async fillAndSubmitForm(page, form) {
    try {
      this.log('INFO', 'Form Filling', 'Starting form fill');

      // Check for CAPTCHA
      if (await this.detectCaptcha(form)) {
        return {
          success: false,
          method: 'form_with_captcha',
          error: 'Form has CAPTCHA - cannot auto-submit'
        };
      }

      // Get all inputs and textareas
      const inputs = await form.$$('input, textarea');
      let filledCount = 0;
      let emailFilled = false;
      let messageFilled = false;

      for (const input of inputs) {
        try {
          const type = await input.getAttribute('type') || 'text';
          const name = (await input.getAttribute('name') || '').toLowerCase();
          const placeholder = (await input.getAttribute('placeholder') || '').toLowerCase();
          const id = (await input.getAttribute('id') || '').toLowerCase();
          
          const fieldText = `${name} ${placeholder} ${id}`;

          // Skip hidden, submit, button
          if (['hidden', 'submit', 'button'].includes(type)) {
            continue;
          }

          // Fill name field
          if (!emailFilled && (name.includes('name') || placeholder.includes('name') || id.includes('name'))) {
            await input.fill(this.contactPerson);
            filledCount++;
            this.log('INFO', 'Field Filled', 'Name field');
            continue;
          }

          // Fill email field
          if (!emailFilled && (type === 'email' || fieldText.includes('email') || fieldText.includes('e-mail'))) {
            await input.fill(this.email);
            emailFilled = true;
            filledCount++;
            this.log('INFO', 'Field Filled', 'Email field');
            continue;
          }

          // Fill phone field
          if (this.phone && (type === 'tel' || fieldText.includes('phone') || fieldText.includes('tel'))) {
            await input.fill(this.phone);
            filledCount++;
            this.log('INFO', 'Field Filled', 'Phone field');
            continue;
          }

          // Fill subject field
          if (fieldText.includes('subject') || fieldText.includes('topic')) {
            await input.fill('Partnership Inquiry');
            filledCount++;
            this.log('INFO', 'Field Filled', 'Subject field');
            continue;
          }

          // Fill message/textarea
          const tagName = await input.evaluate(el => el.tagName.toLowerCase());
          if (tagName === 'textarea' && !messageFilled) {
            if (fieldText.includes('message') || fieldText.includes('comment') || fieldText.includes('inquiry')) {
              await input.fill(this.message);
              messageFilled = true;
              filledCount++;
              this.log('INFO', 'Field Filled', 'Message field');
              continue;
            }
          }
        } catch (e) {
          this.log('WARNING', 'Field Error', e.message);
          continue;
        }
      }

      // Require email and message
      if (!emailFilled || !messageFilled) {
        this.log('WARNING', 'Form Incomplete', `Email: ${emailFilled}, Message: ${messageFilled}`);
        return {
          success: false,
          method: 'incomplete_form',
          error: 'Could not fill required fields',
          fields_filled: filledCount
        };
      }

      // CRITICAL: Dismiss any remaining cookie modals before screenshot
      await this.handleCookieModal(page);
      await page.waitForTimeout(300);

      // Take screenshot before submit
      const screenshotPath = `screenshots/before-submit-${Date.now()}.png`;
      await page.screenshot({ path: screenshotPath, fullPage: false });

      // Find and click submit button
      const submitButton = await form.$('button[type="submit"], input[type="submit"]');
      if (submitButton) {
        await submitButton.click();
        this.log('SUCCESS', 'Form Submitted', `Filled ${filledCount} fields`);
        await page.waitForTimeout(2000); // Wait for submission

        return {
          success: true,
          method: 'form_submitted',
          fields_filled: filledCount,
          screenshot_url: screenshotPath
        };
      } else {
        return {
          success: false,
          method: 'no_submit_button',
          error: 'No submit button found',
          fields_filled: filledCount
        };
      }
    } catch (e) {
      this.log('ERROR', 'Form Submission', e.message);
      return {
        success: false,
        method: 'submission_error',
        error: e.message
      };
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
      // STRATEGY 1: Check homepage
      this.log('INFO', 'Strategy 1', 'Checking homepage for forms');
      await page.goto(this.url, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await this.handleCookieModal(page);
      await page.waitForTimeout(2000);

      let forms = await page.$$('form');
      this.log('INFO', 'Homepage Forms', `Found ${forms.length} forms`);

      if (forms.length > 0) {
        const result = await this.fillAndSubmitForm(page, forms[0]);
        await browser.close();
        return result;
      }

      // STRATEGY 2: Navigate to contact page
      this.log('INFO', 'Strategy 2', 'Looking for contact page');
      const contactLink = await this.findContactLink(page);
      
      if (contactLink) {
        this.log('INFO', 'Contact Link Found', contactLink);
        await page.goto(contactLink, { waitUntil: 'domcontentloaded', timeout: 15000 });
        await this.handleCookieModal(page);
        await page.waitForTimeout(3000); // Wait for React/client-side rendering

        forms = await page.$$('form');
        this.log('INFO', 'Contact Page Forms', `Found ${forms.length} forms`);

        if (forms.length > 0) {
          const result = await this.fillAndSubmitForm(page, forms[0]);
          await browser.close();
          return result;
        }

        // No form but found contact page - extract email
        const emails = await page.$$eval('a[href^="mailto:"]', links =>
          links.map(link => link.href.replace('mailto:', ''))
        );

        if (emails.length > 0) {
          this.log('SUCCESS', 'Email Found', emails[0]);
          await browser.close();
          return {
            success: true,
            method: 'email_found',
            contact_info: { emails }
          };
        }

        this.log('WARNING', 'Contact Page Only', 'No form or email found');
        await browser.close();
        return {
          success: false,
          method: 'contact_page_only',
          error: 'Contact page found but no form or email'
        };
      }

      // STRATEGY 3: Check iframes
      this.log('INFO', 'Strategy 3', 'Checking iframes');
      const iframes = await page.$$('iframe');

      for (const iframe of iframes.slice(0, 2)) {
        try {
          const frame = await iframe.contentFrame();
          if (frame) {
            const iframeForms = await frame.$$('form');
            if (iframeForms.length > 0) {
              this.log('INFO', 'Iframe Form', 'Found form in iframe');
              await browser.close();
              return {
                success: false,
                method: 'form_in_iframe',
                error: 'Form in iframe - may require manual review'
              };
            }
          }
        } catch (e) {
          continue;
        }
      }

      this.log('ERROR', 'No Contact Found', 'No form or contact page found');
      await browser.close();
      return {
        success: false,
        method: 'no_contact_found',
        error: 'No contact form or page found'
      };

    } catch (e) {
      this.log('ERROR', 'Processing Error', e.message);
      await browser.close();
      return {
        success: false,
        method: 'error',
        error: e.message
      };
    }
  }
}

// Main execution
(async () => {
  const args = process.argv.slice(2);
  
  if (args.length < 3) {
    console.error('Usage: node rapid-process-single.js <url> <company_name> <message> [email] [phone] [contact_person]');
    process.exit(1);
  }

  const [url, companyName, message, email, phone, contactPerson] = args;

  const processor = new RapidProcessor(url, companyName, message, email, phone, contactPerson);
  const result = await processor.process();

  // Output JSON to stdout (Python will capture this)
  console.log(JSON.stringify(result, null, 2));
  
  process.exit(result.success ? 0 : 1);
})();
