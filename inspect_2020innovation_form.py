"""
Inspect 2020 Innovation contact form: load the page, find the form (including in iframes),
and print every field with name, id, type, label, required, and select options.
Run from backend: python inspect_2020innovation_form.py
"""
import re
from playwright.sync_api import sync_playwright

URL = "https://www.2020innovation.com/contact"

def get_label_for(el, frame):
    """Get associated label text for an input/select/textarea."""
    try:
        el_id = el.get_attribute("id")
        if el_id:
            label_el = frame.query_selector(f'label[for="{el_id}"]')
            if label_el:
                return (label_el.inner_text() or "").strip()
        parent = el.evaluate_handle("el => el.closest('label')")
        if parent:
            txt = parent.inner_text()
            if txt:
                return (txt or "").strip()
        prev = el.evaluate_handle("el => el.previousElementSibling")
        if prev:
            tag = prev.evaluate("el => el.tagName")
            if tag and tag.lower() == "label":
                return (prev.inner_text() or "").strip()
    except Exception:
        pass
    return ""

def inspect_frame(frame, frame_name="main"):
    """Extract all form fields from a frame."""
    forms = frame.query_selector_all("form")
    if not forms:
        return []
    rows = []
    for form in forms:
        # inputs
        for el in form.query_selector_all("input:not([type=hidden]):not([type=submit]):not([type=button])"):
            try:
                name = el.get_attribute("name") or ""
                id_ = el.get_attribute("id") or ""
                typ = (el.get_attribute("type") or "text").lower()
                label = get_label_for(el, frame)
                required = el.get_attribute("required") is not None or (el.get_attribute("aria-required") == "true")
                rows.append({
                    "frame": frame_name,
                    "tag": "input",
                    "type": typ,
                    "name": name,
                    "id": id_,
                    "label": label[:80] if label else "",
                    "required": required,
                })
            except Exception as e:
                rows.append({"frame": frame_name, "error": str(e)})
        # textareas
        for el in form.query_selector_all("textarea"):
            try:
                name = el.get_attribute("name") or ""
                id_ = el.get_attribute("id") or ""
                label = get_label_for(el, frame)
                required = el.get_attribute("required") is not None or (el.get_attribute("aria-required") == "true")
                rows.append({
                    "frame": frame_name,
                    "tag": "textarea",
                    "type": "textarea",
                    "name": name,
                    "id": id_,
                    "label": label[:80] if label else "",
                    "required": required,
                })
            except Exception as e:
                rows.append({"frame": frame_name, "error": str(e)})
        # selects
        for el in form.query_selector_all("select"):
            try:
                name = el.get_attribute("name") or ""
                id_ = el.get_attribute("id") or ""
                label = get_label_for(el, frame)
                required = el.get_attribute("required") is not None or (el.get_attribute("aria-required") == "true")
                options = []
                for opt in el.query_selector_all("option"):
                    v = opt.get_attribute("value")
                    t = (opt.inner_text() or "").strip()
                    options.append(f"  value={v!r} text={t!r}")
                rows.append({
                    "frame": frame_name,
                    "tag": "select",
                    "type": "select",
                    "name": name,
                    "id": id_,
                    "label": label[:80] if label else "",
                    "required": required,
                    "options": options,
                })
            except Exception as e:
                rows.append({"frame": frame_name, "error": str(e)})
    return rows

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle", timeout=25000)
        page.wait_for_timeout(3000)

        all_rows = []
        # main page
        all_rows.extend(inspect_frame(page, "main"))
        # iframes
        for i, frame in enumerate(page.frames):
            if frame == page.main_frame:
                continue
            name = frame.url or f"frame_{i}"
            if "about:blank" in name:
                name = f"frame_{i}"
            try:
                all_rows.extend(inspect_frame(frame, name[:60]))
            except Exception as e:
                all_rows.append({"frame": name, "error": str(e)})

        browser.close()

    # print report
    print("=" * 80)
    print("2020 INNOVATION CONTACT FORM – ALL FIELDS (name, id, type, label, required)")
    print("=" * 80)
    for r in all_rows:
        if "error" in r:
            print(f"  [ERROR {r.get('frame')}] {r['error']}")
            continue
        req = "REQUIRED" if r.get("required") else "optional"
        print(f"\n  Frame: {r.get('frame', '')}")
        print(f"  Tag: {r.get('tag')}  Type: {r.get('type')}  {req}")
        print(f"  name={r.get('name')!r}  id={r.get('id')!r}")
        print(f"  label={r.get('label')!r}")
        if r.get("options"):
            print("  Options:")
            for o in r["options"]:
                print(o)
    print("\n" + "=" * 80)
    print("SUMMARY (field names / ids for mapping)")
    print("=" * 80)
    for r in all_rows:
        if "error" in r:
            continue
        name = r.get("name") or "(no name)"
        id_ = r.get("id") or "(no id)"
        label = (r.get("label") or "").strip() or "(no label)"
        req = "*" if r.get("required") else ""
        print(f"  {r.get('tag')}  name={name!r}  id={id_!r}  label={label!r}  {req}")

if __name__ == "__main__":
    main()
