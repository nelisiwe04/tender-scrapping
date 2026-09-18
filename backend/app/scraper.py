from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass
from urllib.parse import urljoin

from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PWTimeoutError

from .config import get_settings
from .models import Tender

settings = get_settings()

TABLE_SELECTOR = "table"
ROW_SELECTOR = "table tbody tr"
NEXT_BUTTON_SELECTOR = "a.paginate_button.next, li.paginate_button.next a, a[aria-label='Next']"
LOADING_TEXT_HINTS = ("loading, please wait", "please wait...")


@dataclass
class ScrapeResult:
    tenders: list[Tender]
    pages_scraped: int
    source_url: str


class ScrapeError(Exception):
    pass


def _status_url(base_url: str, status: str) -> str:
    if status not in settings.status_ids:
        raise ValueError(f"Unknown status '{status}'. Valid: {list(settings.status_ids)}")
    return f"{base_url.rstrip('/')}/Home/opportunities?id={settings.status_ids[status]}"


def _row_to_tender(cells: list[str], links: list[str | None]) -> Tender:
    cleaned = [c.strip() for c in cells if c.strip() != ""]
    detail_url = next((l for l in links if l), None)
    tender = Tender(raw_cells=cleaned, detail_url=detail_url)

    if len(cleaned) >= 5:
        tender.category = cleaned[0]
        tender.description = cleaned[1]
        tender.e_submission = cleaned[2]
        tender.advertised_date = cleaned[3]
        tender.closing_date = cleaned[4]
    elif len(cleaned) == 4:
        tender.category = cleaned[0]
        tender.description = cleaned[1]
        tender.advertised_date = cleaned[2]
        tender.closing_date = cleaned[3]
    elif len(cleaned) >= 1:
        tender.description = " | ".join(cleaned)

    return tender


async def _wait_for_table_data(page: Page, timeout_ms: int, previous_signature: str | None = None) -> str:
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_err = None
    while time.monotonic() < deadline:
        try:
            rows = await page.query_selector_all(ROW_SELECTOR)
            row_texts = [(await row.inner_text()).strip() for row in rows]
            data_rows = [t for t in row_texts if t and not any(h in t.lower() for h in LOADING_TEXT_HINTS)]
            signature = "\n".join(data_rows)
            if data_rows and signature != previous_signature:
                return signature
        except Exception as exc:
            last_err = exc
        await asyncio.sleep(0.5)
    raise ScrapeError(f"Timed out waiting for table. Last error: {last_err}")


async def _extract_current_page_rows(page: Page) -> list[Tender]:
    rows = await page.query_selector_all(ROW_SELECTOR)
    tenders: list[Tender] = []
    for row in rows:
        cells_el = await row.query_selector_all("td")
        if not cells_el:
            continue
        cells_text = [await c.inner_text() for c in cells_el]
        links: list[str | None] = []
        for c in cells_el:
            a = await c.query_selector("a")
            if a:
                href = await a.get_attribute("href")
                links.append(urljoin(page.url, href) if href else None)
        joined = " ".join(cells_text).strip().lower()
        if not joined or any(h in joined for h in LOADING_TEXT_HINTS):
            continue
        tenders.append(_row_to_tender(cells_text, links))
    return tenders


async def _go_to_next_page(page: Page) -> bool:
    btn = await page.query_selector(NEXT_BUTTON_SELECTOR)
    if not btn:
        return False
    is_disabled = await btn.evaluate(
        "el => el.closest('li') ? el.closest('li').classList.contains('disabled') : el.classList.contains('disabled')"
    )
    if is_disabled:
        return False
    await btn.evaluate("el => el.click()")
    return True


async def _dismiss_popups(page: Page) -> None:
    selectors = [
        "#educationalPopup .close",
        "#educationalPopup button.close",
        "#educationalPopup button[data-dismiss='modal']",
        "#educationalPopup button[data-bs-dismiss='modal']",
        "#educationalPopup .btn-close",
        "#educationalPopup .btn-primary",
        "div.modal.show button.close",
        "div.modal.show .btn-close",
    ]
    for sel in selectors:
        try:
            btn = await page.query_selector(sel)
            if btn:
                await btn.evaluate("el => el.click()")
                print(f"[POPUP] Dismissed via {sel}")
                await asyncio.sleep(0.4)
                break
        except Exception:
            continue

    try:
        await page.evaluate("""
            () => {
                document.querySelectorAll('.modal.show, .modal-backdrop').forEach(el => el.remove());
                document.body.classList.remove('modal-open');
                document.body.style.overflow = '';
                document.body.style.paddingRight = '';
            }
        """)
        print("[POPUP] Force-cleaned any remaining modals")
    except Exception:
        pass

    await asyncio.sleep(0.3)


async def _scrape_expanded_rows(page: Page, tenders: list[Tender]) -> None:
    rows = await page.query_selector_all(ROW_SELECTOR)

    parent_rows = []
    for row in rows:
        has_expander = await row.query_selector(
            "td.details-control, td.expand, td:first-child i.fa-plus, td:first-child i.fa-expand"
        )
        if has_expander:
            parent_rows.append(row)

    print(f"[DETAIL] Found {len(parent_rows)} parent rows with expander icons")

    for i, row in enumerate(parent_rows):
        if i >= len(tenders):
            break

        tender = tenders[i]

        try:
            expander = await row.query_selector(
                "td.details-control, td.expand, td:first-child"
            )
            if not expander:
                continue

            await _dismiss_popups(page)

            await expander.evaluate("el => el.click()")
            await asyncio.sleep(0.8)

            detail_handle = await row.evaluate_handle("el => el.nextElementSibling")
            if not detail_handle:
                print(f"[DETAIL] Row {i}: no sibling detail row after expand")
                continue

            detail_el = detail_handle.as_element()
            if detail_el is None:
                continue

            detail_text = await detail_el.inner_text()

            def extract(label: str) -> str | None:
                for line in detail_text.splitlines():
                    line = line.strip()
                    if line.lower().startswith(label.lower()):
                        value = line[len(label):].strip().lstrip(":").strip()
                        return value or None
                return None

            tender.tender_number = extract("Tender Number")
            tender.organ_of_state = extract("Organ Of State")
            tender.tender_type = extract("Tender Type")
            tender.province = extract("Province")
            tender.published_date = extract("Date Published")
            tender.location = extract("Place where goods, works or services are required")
            tender.special_conditions = extract("Special Conditions")

            tender.contact_person = extract("Contact Person")
            tender.contact_email = extract("Email")
            tender.contact_telephone = extract("Telephone number")
            tender.contact_fax = extract("FAX Number")

            brief_yn = extract("Is there a briefing session?")
            comp_yn = extract("Is it compulsory?")
            tender.has_briefing = bool(brief_yn and "yes" in brief_yn.lower())
            tender.is_compulsory = bool(comp_yn and "yes" in comp_yn.lower())
            if tender.has_briefing:
                tender.briefing_datetime = extract("Briefing Date and Time")
                tender.briefing_venue = extract("Briefing Venue")

            doc_links = await detail_el.query_selector_all("a[href]")
            for link in doc_links:
                href = await link.get_attribute("href")
                if not href:
                    continue
                low = href.lower()
                if not any(ext in low for ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx")):
                    continue
                name = (await link.inner_text()).strip()
                tender.documents.append({
                    "name": name or href.split("/")[-1],
                    "type": href.split(".")[-1].upper(),
                    "url": urljoin(page.url, href),
                    "date_uploaded": tender.published_date or "",
                })

            print(
                f"[DETAIL] Row {i+1}/{len(parent_rows)}: "
                f"#{tender.tender_number!r} | docs={len(tender.documents)}"
            )

        except Exception as exc:
            print(f"[DETAIL ERROR] Row {i}: {exc}")
            continue


async def scrape_tenders(
    status: str = "current",
    max_pages: int | None = None,
    keyword: str | None = None,
    base_url: str | None = None,
    fetch_details: bool = True,
) -> ScrapeResult:
    try:
        return await _scrape_tenders(status, max_pages, keyword, base_url, fetch_details)
    except ScrapeError:
        raise
    except Exception as exc:
        raise ScrapeError(f"Unable to start browser scraper: {type(exc).__name__}: {exc}") from exc


async def _scrape_tenders(
    status: str = "current",
    max_pages: int | None = None,
    keyword: str | None = None,
    base_url: str | None = None,
    fetch_details: bool = True,
) -> ScrapeResult:
    cfg = get_settings()

    if sys.platform == "win32" and "SelectorEventLoop" in type(asyncio.get_running_loop()).__name__:
        raise ScrapeError("Playwright requires Windows Proactor loop. Start uvicorn without --reload.")

    base = base_url or cfg.base_url
    url = _status_url(base, status)
    pages_cap = min(max_pages or cfg.max_pages_default, cfg.max_pages_hard_cap)

    async with async_playwright() as pw:
        browser: Browser | None = None
        try:
            print(f"[SCRAPER] Opening: {url}")
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=cfg.user_agent)
            page = await context.new_page()

            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            await _dismiss_popups(page)

            table_signature = await _wait_for_table_data(page, cfg.table_wait_timeout_ms)

            all_tenders: list[Tender] = []
            pages_scraped = 0

            for page_number in range(pages_cap):
                print(f"[SCRAPER] Scraping listing page {page_number + 1}/{pages_cap}")
                page_tenders = await _extract_current_page_rows(page)
                all_tenders.extend(page_tenders)
                pages_scraped += 1

                if fetch_details and page_tenders:
                    print(f"[SCRAPER] Expanding {len(page_tenders)} rows for details...")
                    await _scrape_expanded_rows(page, page_tenders)
                    await asyncio.sleep(0.5)

                if page_number + 1 >= pages_cap:
                    break

                await _dismiss_popups(page)

                moved = await _go_to_next_page(page)
                if not moved:
                    break

                await asyncio.sleep(1.0)
                await _dismiss_popups(page)

                try:
                    table_signature = await _wait_for_table_data(
                        page, cfg.table_wait_timeout_ms, previous_signature=table_signature
                    )
                except ScrapeError:
                    break

            if keyword:
                needle = keyword.lower()
                all_tenders = [
                    t for t in all_tenders
                    if (t.category and needle in t.category.lower())
                    or (t.description and needle in t.description.lower())
                ]

            print(f"[SCRAPER] Done. Total: {len(all_tenders)}")
            return ScrapeResult(tenders=all_tenders, pages_scraped=pages_scraped, source_url=url)

        except PWTimeoutError as exc:
            raise ScrapeError(f"Playwright timeout: {repr(exc)}") from exc
        except ScrapeError:
            raise
        except Exception as exc:
            raise ScrapeError(f"Scraping failed: {type(exc).__name__}: {repr(exc)}") from exc
        finally:
            if browser is not None:
                await browser.close()