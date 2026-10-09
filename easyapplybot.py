import time, random, os, csv, platform, argparse, sys
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import pandas as pd
import pyautogui
from fake_useragent import UserAgent
from urllib.request import urlopen
from webdriver_manager.chrome import ChromeDriverManager
import re
import yaml
from datetime import datetime, timedelta
from selenium.webdriver.common.action_chains import ActionChains

log = logging.getLogger(__name__)

ua = UserAgent(platforms='pc')
user_agent = ua.random
print(user_agent)

options = Options()

# Disable webdriver flags or you will be easily detectable
options.add_argument("--start-maximized")
options.add_argument("--ignore-certificate-errors")
options.add_argument('--no-sandbox')
options.add_argument("--disable-extensions")
options.add_argument("--disable-blink-features")
options.add_argument(f'--user-agent={user_agent}')
options.add_argument('--disable-blink-features=AutomationControlled')
options.add_experimental_option("useAutomationExtension", False)
options.add_experimental_option("excludeSwitches",["enable-automation"])

# todo: running on selenium grid doesn't work atm due to pytautogui lock avoidance
# driver = webdriver.Remote(command_executor='http://localhost:4444', options=options)
driver = webdriver.Chrome(options=options)



def setupLogger() -> None:
    dt: str = datetime.strftime(datetime.now(), "%m_%d_%y %H_%M_%S_")

    if not os.path.isdir('./logs'):
        os.mkdir('./logs')

    logging.basicConfig(filename=('./logs/' + str(dt) + 'applyJobs.log'), filemode='w',
                        format='%(asctime)s::%(name)s::%(levelname)s::%(message)s', datefmt='./logs/%d-%b-%y %H:%M:%S')
    log.setLevel(logging.DEBUG)
    c_handler = logging.StreamHandler()
    c_handler.setLevel(logging.DEBUG)
    c_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%H:%M:%S')
    c_handler.setFormatter(c_format)
    log.addHandler(c_handler)


class EasyApplyBot:
    setupLogger()
    # MAX_SEARCH_TIME is 10 hours by default, feel free to modify it
    MAX_SEARCH_TIME = 20 * 60 * 60

    def __init__(self,
                 username,
                 password,
                 phone_number,
                 uploads={},
                 filename='output.csv',
                 blacklist=[],
                 blackListTitles=[],
                 dry_run: bool = True,
                 daily_cap: int = 25) -> None:

        log.info("Welcome to Easy Apply Bot")
        dirpath: str = os.getcwd()
        log.info("current directory is : " + dirpath)
        log.info(f"Mode: {'DRY-RUN (no submits)' if dry_run else 'LIVE'}  Daily cap: {daily_cap}")

        self.uploads = uploads
        past_ids: list | None = self.get_appliedIDs(filename)
        self.appliedJobIDs: list = past_ids if past_ids != None else []
        self.filename: str = filename
        # self.options = self.browser_options()
        self.browser = driver
        self.wait = WebDriverWait(self.browser, 30)
        self.blacklist = blacklist
        self.blackListTitles = blackListTitles
        self.dry_run = dry_run
        self.daily_cap = daily_cap
        self.submitted_today = 0
        self.start_linkedin(username, password)
        self.phone_number = phone_number
        self.checked_invalid = False

    def get_appliedIDs(self, filename) -> list | None:
        try:
            df = pd.read_csv(filename,
                             header=None,
                             names=['timestamp', 'jobID', 'job', 'company', 'attempted', 'result'],
                             lineterminator='\n',
                             encoding='utf-8')

            df['timestamp'] = pd.to_datetime(df['timestamp'], format="%Y-%m-%d %H:%M:%S")
            df = df[df['timestamp'] > (datetime.now() - timedelta(days=2))]
            jobIDs: list = list(df.jobID)
            log.info(f"{len(jobIDs)} jobIDs found")
            return jobIDs
        except Exception as e:
            log.info(str(e) + "   jobIDs could not be loaded from CSV {}".format(filename))
            return None

    def _find_visible(self, by, selector: str, timeout: int = 30):
        end = time.time() + timeout
        while time.time() < end:
            for el in self.browser.find_elements(by, selector):
                try:
                    if el.is_displayed() and el.is_enabled():
                        return el
                except Exception:
                    continue
            time.sleep(0.5)
        raise TimeoutException(f"No visible element for: {selector}")

    def _find_visible_input(self, selectors: list, timeout: int = 30):
        end = time.time() + timeout
        while time.time() < end:
            for sel in selectors:
                for el in self.browser.find_elements(By.CSS_SELECTOR, sel):
                    try:
                        if el.is_displayed() and el.is_enabled():
                            return el
                    except Exception:
                        continue
            time.sleep(0.5)
        raise TimeoutException(f"No visible element matched: {selectors}")

    def _type_into(self, el, text: str) -> None:
        self.browser.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        self.browser.execute_script("arguments[0].focus();", el)
        try:
            el.send_keys(text)
        except Exception:
            self.browser.execute_script(
                "const el=arguments[0], v=arguments[1];"
                "const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
                "s.call(el, v);"
                "el.dispatchEvent(new Event('input',{bubbles:true}));"
                "el.dispatchEvent(new Event('change',{bubbles:true}));",
                el, text,
            )

    def start_linkedin(self, username, password) -> None:
        log.info("Logging in.....Please wait :)  ")
        self.browser.get("https://www.linkedin.com/login?trk=guest_homepage-basic_nav-header-signin")
        try:
            user_field = self._find_visible_input([
                'input[autocomplete~="username"]',
                'input[name="session_key"]',
                '#username',
                'input[type="email"]',
            ])
            self._type_into(user_field, username)
            time.sleep(1)
            pw_field = self._find_visible_input([
                'input[autocomplete="current-password"]',
                'input[name="session_password"]',
                '#password',
                'input[type="password"]',
            ])
            self._type_into(pw_field, password)
            time.sleep(1)
            sign_in_btn = self._find_visible(
                By.XPATH,
                '//button[@type="submit"'
                ' or .//span[normalize-space()="Sign in"]'
                ' or normalize-space()="Sign in"]',
            )
            try:
                sign_in_btn.click()
            except Exception:
                self.browser.execute_script("arguments[0].click();", sign_in_btn)
            time.sleep(3)
            self._handle_post_login()
        except TimeoutException:
            log.info("TimeoutException! Username/password field or login button not found")
            log.info(f"Current URL: {self.browser.current_url}")
            try:
                os.makedirs("./logs", exist_ok=True)
                shot_path = f"./logs/login_fail_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                self.browser.save_screenshot(shot_path)
                log.info(f"Saved screenshot: {shot_path}")
            except Exception as e:
                log.info(f"Failed to save screenshot: {e}")

    def _handle_post_login(self) -> None:
        """Detect LinkedIn security checkpoints and pause for human handoff.

        Polls the URL until the checkpoint clears (or times out at 10 min), so
        this works whether or not we have a TTY.
        """
        checkpoint_markers = ("/checkpoint/", "/uas/consumer-protection", "/authwall")

        def on_checkpoint() -> bool:
            try:
                return any(m in self.browser.current_url for m in checkpoint_markers)
            except Exception:
                return False

        url = self.browser.current_url
        log.info(f"Post-login URL: {url}")
        if not on_checkpoint():
            return

        os.makedirs("./logs", exist_ok=True)
        shot = f"./logs/checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        try:
            self.browser.save_screenshot(shot)
        except Exception:
            pass
        log.warning(
            "LinkedIn security checkpoint detected. "
            "Clear the challenge in the browser window — I'll auto-resume when the URL changes."
        )
        log.warning(f"Screenshot: {shot}  URL: {url}")

        deadline = time.time() + 10 * 60
        while time.time() < deadline:
            if not on_checkpoint():
                log.info(f"Checkpoint cleared. Current URL: {self.browser.current_url}")
                return
            time.sleep(3)
        log.error("Checkpoint not cleared within 10 minutes; aborting.")
        sys.exit(2)

    def fill_data(self) -> None:
        # Previously shrank window to 1x1 and parked it off-screen. That broke
        # every is_displayed() visibility check and is a classic bot signal.
        # Keep the window at a normal human resolution.
        try:
            self.browser.set_window_size(1440, 900)
            self.browser.set_window_position(0, 0)
        except Exception:
            pass

    def start_apply(self, positions, locations) -> None:
        start: float = time.time()
        self.fill_data()

        

        combos: list = []
        while len(combos) < len(positions) * len(locations):
            position = positions[random.randint(0, len(positions) - 1)]
            location = locations[random.randint(0, len(locations) - 1)]
            combo: tuple = (position, location)
            if combo not in combos:
                combos.append(combo)
                log.info(f"Applying to {position}: {location}")
                location = "&location=" + location
                self.applications_loop(position, location)
            if len(combos) > 500:
                break

    def applications_loop(self, position, location):

        count_application = 0
        count_job = 0
        jobs_per_page = 0
        start_time: float = time.time()

        log.info("Looking for jobs.. Please wait..")

        self.browser.set_window_position(1, 1)
        self.browser.maximize_window()
        self.browser, _ = self.next_jobs_page(position, location, jobs_per_page)
        log.info("Looking for jobs.. Please wait..")

        empty_cycles = 0
        while time.time() - start_time < self.MAX_SEARCH_TIME:
            log.debug(f"Current URL: {self.browser.current_url}")
            if 'linkedin' not in self.browser.current_url:
                self.browser.switch_to.window(self.browser.window_handles[0])
            try:
                log.info(f"{(self.MAX_SEARCH_TIME - (time.time() - start_time)) // 60} minutes left in this search")

                time.sleep(random.uniform(2.0, 3.5))
                # Scroll the virtualized job-list container so lazy cards render.
                try:
                    self.browser.execute_script(
                        "const sels=['ul.scaffold-layout__list-container','div.jobs-search-results-list','.jobs-search-results__list'];"
                        "for (const s of sels) { const el=document.querySelector(s); if (el) { el.scrollTop = el.scrollHeight; break; } }"
                    )
                except Exception:
                    pass
                time.sleep(1.0)

                links = self.browser.find_elements(By.XPATH, '//div[@data-job-id]')
                log.info(f"Found {len(links)} job cards on page")
                if len(links) == 0:
                    log.info("No job cards found; ending this search")
                    break

                IDs: list = []
                for link in links:
                    jid = link.get_attribute("data-job-id") or ""
                    jid = jid.strip()
                    if jid.lstrip('-').isdigit():
                        IDs.append(int(jid))

                # Dedup preserving order, then drop already-applied.
                seen = set()
                unique_ids = [x for x in IDs if not (x in seen or seen.add(x))]
                jobIDs = [j for j in unique_ids if j not in self.appliedJobIDs]
                log.info(f"Extracted {len(unique_ids)} unique IDs, {len(jobIDs)} new to attempt")

                if not jobIDs:
                    empty_cycles += 1
                    log.info(f"No new jobs on page (empty cycle {empty_cycles}); advancing")
                    if empty_cycles >= 3:
                        log.warning("3 consecutive empty cycles; moving to next search combo")
                        break
                    jobs_per_page += 25
                    count_job = 0
                    self.browser, jobs_per_page = self.next_jobs_page(position, location, jobs_per_page)
                    continue
                empty_cycles = 0
                # loop over IDs to apply
                for i, jobID in enumerate(jobIDs):
                    count_job += 1
                    self.get_job_page(jobID)

                    button = self.get_easy_apply_button()

                    if button is not False:
                        string_easy = "* has Easy Apply Button"
                        log.info("Clicking the EASY apply button")
                        time.sleep(3)
                        #self.fill_out_phone_number()
                        result: bool = self.send_resume()
                        count_application += 1
                    else:
                        log.info("The button does not exist.")
                        string_easy = "* Doesn't have Easy Apply Button"
                        result = False

                    position_number: str = str(count_job + jobs_per_page)
                    log.info(f"\nPosition {position_number}:\n {self.browser.title} \n {string_easy} \n")

                    self.write_to_file(button, jobID, self.browser.title, result)

                    # sleep every 20 applications
                    if count_application != 0 and count_application % 20 == 0:
                        sleepTime: int = random.randint(300, 500)
                        log.info(f"""********count_application: {count_application}************\n\n
                                    Time for a nap - see you in:{int(sleepTime / 60)} min
                                ****************************************\n\n""")
                        time.sleep(sleepTime)

                    # go to new page if all jobs are done
                    if count_job == len(jobIDs):
                        jobs_per_page = jobs_per_page + 25
                        count_job = 0
                        log.info("""****************************************\n\n
                        Going to next jobs page, YEAAAHHH!!
                        ****************************************\n\n""")
                        self.avoid_lock()
                        self.browser, jobs_per_page = self.next_jobs_page(position,
                                                                        location,
                                                                        jobs_per_page)
            except Exception:
                log.exception("Exception in main application loop")

    def write_to_file(self, button, jobID, browserTitle, result) -> None:
        def re_extract(text, pattern):
            target = re.search(pattern, text)
            if target:
                target = target.group(1)
            return target

        timestamp: str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        attempted: bool = False if button == False else True
        job = re_extract(browserTitle.split(' | ')[0], r"\(?\d?\)?\s?(\w.*)")
        company = re_extract(browserTitle.split(' | ')[1], r"(\w.*)")

        toWrite: list = [timestamp, jobID, job, company, attempted, result]
        with open(self.filename, 'a') as f:
            writer = csv.writer(f)
            writer.writerow(toWrite)

    def get_job_page(self, jobID):
        job: str = 'https://www.linkedin.com/jobs/view/' + str(jobID)
        self.browser.get(job)
        self.job_page = self.load_page(sleep=0.5)
        return self.job_page

    def get_easy_apply_button(self):
        try:
            button = self.browser.find_elements("xpath", '//*[contains(@aria-label, "Easy Apply to")]')
            if len(button) == 0:
                return False

            javascript = """
            let elements = Array.from(document.querySelectorAll('button[aria-label]'));
            let targetElement = elements.find(el => el.getAttribute('aria-label').includes('Easy Apply to'));
            if (targetElement) {
                targetElement.click();
            }
            """

            self.browser.execute_script(javascript)
            time.sleep(1)
            return True
        except Exception as e:
            log.error("exception in get_easy_apply_button", e)
            return False        

    # def fill_out_phone_number(self):
    #     def is_present(button_locator) -> bool:
    #         return len(self.browser.find_elements(button_locator[0],
    #                                               button_locator[1])) > 0
    #     # try:
    #     next_locater = (By.CSS_SELECTOR,
    #                     "button[aria-label='Continue to next step']")
    #     input_field = self.browser.find_element("xpath", "//input[contains(@id,'phoneNumber')]")


    #     if input_field:
    #         input_field.clear()
    #         input_field.send_keys(self.phone_number)
    #         time.sleep(random.uniform(4.5, 6.5))
        


    #         next_locater = (By.CSS_SELECTOR,
    #                         "button[aria-label='Continue to next step']")
    #         error_locator = (By.CLASS_NAME,
    #                          "artdeco-inline-feedback__message")

    #         # Click Next or submitt button if possible
    #         button: None = None
    #         if is_present(next_locater):
    #             button: None = self.wait.until(EC.element_to_be_clickable(next_locater))

    #         if is_present(error_locator):
    #             for element in self.browser.find_elements(error_locator[0],
    #                                                         error_locator[1]):
    #                 text = element.text
    #                 if "Please enter" in text:
    #                     button = None
    #                     break
    #         if button:
    #             button.click()
    #             time.sleep(random.uniform(1.5, 2.5))
    #             # if i in (3, 4):
    #             #     submitted = True
    #             # if i != 2:
    #             #     break



    #     else:
    #         log.debug(f"Could not find phone number field")
                


    # CSS selector that matches the Easy Apply modal container across old & new
    # LinkedIn UIs. The data-sdui-screen attr is the most reliable anchor on the
    # current (2026) SDUI build; the others cover older markup and fallbacks.
    MODAL_SELECTOR = (
        "[data-sdui-screen*='EasyApply'], "
        "[data-testid='dialog-content'], "
        "div.jobs-easy-apply-modal, "
        "div[role='dialog']"
    )

    def _dump_modal_state(self, tag: str) -> None:
        """Save screenshot + modal HTML to logs for inspection."""
        try:
            os.makedirs("./logs", exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            shot = f"./logs/{tag}_{ts}.png"
            html_path = f"./logs/{tag}_{ts}.html"
            try:
                self.browser.save_screenshot(shot)
            except Exception as e:
                log.info(f"screenshot failed: {e}")
            try:
                modal_html = self.browser.execute_script(
                    "const sels=arguments[0];"
                    "for (const s of sels.split(',')) {"
                    "  const el=document.querySelector(s.trim());"
                    "  if (el) return el.outerHTML;"
                    "}"
                    "return document.documentElement.outerHTML;",
                    self.MODAL_SELECTOR,
                )
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(modal_html)
            except Exception as e:
                log.info(f"html dump failed: {e}")
            log.info(f"Dumped modal state: {shot} / {html_path}")
        except Exception as e:
            log.info(f"_dump_modal_state failure: {e}")

    def _find_modal_action_button(self):
        """Find the primary action button in the Easy Apply modal.

        Returns (element, kind, info) where kind is one of:
          'next'   -> Next / Continue to next step
          'review' -> Review your application
          'submit' -> Submit application
          'follow' -> Follow-company checkbox label
        or (None, None, info) if nothing actionable visible.
        """
        js = r"""
        const sels = arguments[0];
        let modal = null;
        for (const s of sels.split(',')) { modal = document.querySelector(s.trim()); if (modal) break; }
        const root = modal || document;
        const buttons = Array.from(root.querySelectorAll('button'));
        const visible = (el) => {
          const r = el.getBoundingClientRect();
          const s = window.getComputedStyle(el);
          return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && !el.disabled;
        };
        const score = (el) => {
          const al = (el.getAttribute('aria-label') || '').toLowerCase();
          const tx = (el.textContent || '').trim().toLowerCase();
          if (al.includes('submit application') || tx === 'submit application') return 'submit';
          if (al.includes('review your application') || tx === 'review') return 'review';
          if (al.includes('continue to next step') || tx === 'next' || tx === 'continue') return 'next';
          return null;
        };
        // Prefer buttons inside a <footer> (modal action bar) when present.
        const footerButtons = Array.from(root.querySelectorAll('footer button'));
        const ordered = footerButtons.concat(buttons.filter(b => !footerButtons.includes(b)));
        for (const b of ordered) {
          if (!visible(b)) continue;
          const k = score(b);
          if (k) {
            // Stamp a marker so Python can re-locate reliably.
            b.setAttribute('data-ea-marker', 'action');
            return {kind: k, text: (b.textContent||'').trim(), aria: b.getAttribute('aria-label'), modalFound: !!modal};
          }
        }
        const followLabel = (modal || document).querySelector("label[for='follow-company-checkbox']");
        if (followLabel) { followLabel.setAttribute('data-ea-marker','follow'); return {kind: 'follow', text: 'follow', modalFound: !!modal}; }
        return {kind: null, modalFound: !!modal};
        """
        info = self.browser.execute_script(js, self.MODAL_SELECTOR)
        if not info or not info.get("kind"):
            return None, None, info or {}
        kind = info["kind"]
        marker = "follow" if kind == "follow" else "action"
        try:
            el = self.browser.find_element(By.CSS_SELECTOR, f"[data-ea-marker='{marker}']")
            return el, kind, info
        except Exception:
            return None, None, info

    def _auto_fill_modal(self) -> int:
        """Fill unanswered required fields in the modal with conservative defaults.

        Returns count of fields filled. Covers:
          - text/number inputs → '3' (most prompts are "years of ..." experience)
          - Yes/No radios → 'Yes' for positive-eligibility prompts (auth to work,
            US resident, degree), 'No' for negative prompts (require sponsorship,
            felony), otherwise 'Yes'
          - multi-option radios → first option (or decline-to-self-identify)
          - selects → first non-placeholder option
        React/SDUI inputs require native 'input'/'change' events, not just a
        .value assignment, so we dispatch them via native setters.
        """
        js = r"""
        const sels = arguments[0];
        let modal = null;
        for (const s of sels.split(',')) { modal = document.querySelector(s.trim()); if (modal) break; }
        if (!modal) return 0;

        const nativeSetValue = (el, v) => {
          const proto = el.tagName === 'TEXTAREA'
            ? window.HTMLTextAreaElement.prototype
            : el.tagName === 'SELECT'
              ? window.HTMLSelectElement.prototype
              : window.HTMLInputElement.prototype;
          const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
          setter.call(el, v);
          el.dispatchEvent(new Event('input', {bubbles: true}));
          el.dispatchEvent(new Event('change', {bubbles: true}));
        };

        let filled = 0;

        // --- Text / number inputs ---
        for (const input of modal.querySelectorAll('input[type=text], input[type=number], input[inputmode=numeric]')) {
          if (input.value && input.value.trim().length > 0) continue;
          const label = (input.getAttribute('aria-label') || '').toLowerCase();
          let v = '3';
          if (/salary|compensation|rate|pay|wage/.test(label)) v = '150000';
          else if (/notice period|notice/.test(label)) v = '2';
          else if (/zip|postal/.test(label)) v = '92101';
          else if (/url|website|linkedin|portfolio|github/.test(label)) v = 'https://linkedin.com/in/jareddzwick';
          else if (/years|how many|yrs/.test(label)) v = '3';
          nativeSetValue(input, v);
          filled++;
        }

        // --- Textareas ---
        for (const ta of modal.querySelectorAll('textarea')) {
          if (ta.value && ta.value.trim().length > 0) continue;
          nativeSetValue(ta, 'See attached resume.');
          filled++;
        }

        // --- Radio groups ---
        const radios = Array.from(modal.querySelectorAll('input[type=radio]'));
        const groups = {};
        for (const r of radios) {
          const n = r.name || r.getAttribute('name') || r.id;
          (groups[n] = groups[n] || []).push(r);
        }
        for (const name of Object.keys(groups)) {
          const group = groups[name];
          if (group.some(r => r.checked)) continue;
          // Find question label — the <p> text just above the fieldset.
          const fs = group[0].closest('fieldset');
          const qContainer = fs ? fs.parentElement : group[0].parentElement;
          const qText = (qContainer ? (qContainer.innerText || '') : '').toLowerCase();

          // Enumerate option labels in order.
          const optLabels = group.map(r => {
            const lab = r.closest('div') ? r.closest('div').parentElement.innerText : '';
            return (lab || '').trim().toLowerCase();
          });

          const pick = (predicate) => {
            for (let i = 0; i < optLabels.length; i++) if (predicate(optLabels[i])) return i;
            return -1;
          };

          let idx = -1;
          const isYesNo = optLabels.some(l => l.includes('yes')) && optLabels.some(l => l.includes('no'));
          if (isYesNo) {
            // Prompts where "No" is the safer / correct answer.
            if (/sponsor|visa|h1b|h-1b|require.*visa|need.*sponsor|felony|conviction|criminal/.test(qText)) {
              idx = pick(l => l.includes('no'));
            } else {
              // Default employability answer.
              idx = pick(l => l.includes('yes'));
            }
          } else {
            // Multi-option: prefer "decline to self identify" / "prefer not" for EEO,
            // otherwise first option.
            idx = pick(l => l.includes('decline') || l.includes('prefer not'));
            if (idx < 0) idx = 0;
          }
          if (idx < 0) idx = 0;
          const chosen = group[idx];
          chosen.checked = true;
          chosen.dispatchEvent(new Event('click', {bubbles: true}));
          chosen.dispatchEvent(new Event('change', {bubbles: true}));
          // Also click the associated label — some SDUI handlers listen there.
          const lbl = modal.querySelector(`label[for='${chosen.id}']`);
          if (lbl) lbl.click();
          filled++;
        }

        // --- Selects ---
        for (const sel of modal.querySelectorAll('select')) {
          if (sel.value && sel.value.trim().length > 0 && sel.selectedIndex > 0) continue;
          const opts = Array.from(sel.options);
          // Skip the placeholder (usually index 0 with empty value).
          const target = opts.find((o,i) => i > 0 && o.value && o.value.trim().length > 0);
          if (!target) continue;
          nativeSetValue(sel, target.value);
          filled++;
        }

        // --- Checkboxes (acknowledgments / consent) ---
        for (const cb of modal.querySelectorAll('input[type=checkbox]')) {
          if (cb.checked) continue;
          // Skip the "follow company" checkbox — handled elsewhere, not required.
          if (cb.id === 'follow-company-checkbox') continue;
          const lbl = modal.querySelector(`label[for='${cb.id}']`);
          if (lbl) {
            lbl.click();
          } else {
            cb.checked = true;
            cb.dispatchEvent(new Event('click', {bubbles: true}));
            cb.dispatchEvent(new Event('change', {bubbles: true}));
          }
          filled++;
        }

        return filled;
        """
        try:
            return int(self.browser.execute_script(js, self.MODAL_SELECTOR) or 0)
        except Exception as e:
            log.info(f"_auto_fill_modal failed: {e}")
            return 0

    def _has_form_errors(self) -> bool:
        """Detect validation errors in the modal (old + new SDUI markup)."""
        js = r"""
        const sels = arguments[0];
        let modal = null;
        for (const s of sels.split(',')) { modal = document.querySelector(s.trim()); if (modal) break; }
        const root = modal || document;
        if (root.querySelector('.artdeco-inline-feedback--error')) return true;
        if (root.querySelector('[type*="error-pebble-icon"]')) return true;
        if (root.querySelector('[aria-invalid="true"]')) return true;
        const text = (root.innerText || '').toLowerCase();
        const needles = ['this field is required', 'invalid input',
                         'please enter', 'please make', 'please select', 'enter a '];
        return needles.some(n => text.includes(n));
        """
        try:
            return bool(self.browser.execute_script(js, self.MODAL_SELECTOR))
        except Exception:
            return False

    def _dismiss_easy_apply_modal(self) -> None:
        """Close the modal + discard draft (used when we bail on a job)."""
        try:
            close_btns = self.browser.find_elements(By.CSS_SELECTOR, "button[aria-label='Dismiss']")
            for b in close_btns:
                if b.is_displayed():
                    b.click()
                    time.sleep(0.8)
                    break
            discard_btns = self.browser.find_elements(By.XPATH, "//button[.//span[normalize-space()='Discard']]")
            for b in discard_btns:
                if b.is_displayed():
                    b.click()
                    time.sleep(0.5)
                    break
        except Exception as e:
            log.info(f"modal dismiss failed: {e}")

    def send_resume(self) -> bool:
        """Walk the Easy Apply modal step-by-step.

        Bounded loop (max MAX_STEPS iterations with per-step wait) so a stuck
        modal can't spin until Chrome crashes the tab.
        """
        MAX_STEPS = 20
        STEP_WAIT_SEC = 15
        submitted = False
        try:
            time.sleep(random.uniform(1.5, 2.5))
            # Wait for the modal itself to render before touching anything.
            try:
                self.wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, self.MODAL_SELECTOR)
                ))
            except TimeoutException:
                log.warning("Easy Apply modal did not open; dumping state and bailing.")
                self._dump_modal_state("no_modal")
                return False

            last_kind = None
            same_kind_count = 0
            for step in range(MAX_STEPS):
                # Give the modal a moment to settle after a click.
                deadline = time.time() + STEP_WAIT_SEC
                button = kind = info = None
                while time.time() < deadline:
                    button, kind, info = self._find_modal_action_button()
                    if button is not None:
                        break
                    time.sleep(0.5)

                if button is None:
                    log.warning(f"Step {step}: no actionable button in modal. info={info}")
                    self._dump_modal_state(f"no_button_step{step}")
                    self._dismiss_easy_apply_modal()
                    return False

                log.info(f"Step {step}: action='{kind}' aria='{info.get('aria')}' text='{info.get('text')}'")

                # Fill any unanswered fields before trying to advance.
                filled = self._auto_fill_modal()
                if filled > 0:
                    log.info(f"Step {step}: auto-filled {filled} field(s); re-checking action button.")
                    time.sleep(0.5)
                    button2, kind2, info2 = self._find_modal_action_button()
                    if button2 is not None:
                        button, kind, info = button2, kind2, info2

                if self._has_form_errors():
                    log.warning(f"Step {step}: form errors visible after auto-fill — skipping job.")
                    self._dump_modal_state(f"form_errors_step{step}")
                    self._dismiss_easy_apply_modal()
                    return False

                if kind == "submit":
                    if self.dry_run:
                        log.info("DRY-RUN: not clicking Submit; dismissing modal.")
                        self._dump_modal_state(f"dryrun_submit_step{step}")
                        self._dismiss_easy_apply_modal()
                        return True
                    if self.submitted_today >= self.daily_cap:
                        log.warning(f"Daily cap reached ({self.submitted_today}/{self.daily_cap}); not submitting.")
                        self._dismiss_easy_apply_modal()
                        return False

                # Scroll into view and click.
                try:
                    self.browser.execute_script("arguments[0].scrollIntoView({block:'center'});", button)
                    button.click()
                except Exception:
                    try:
                        self.browser.execute_script("arguments[0].click();", button)
                    except Exception as e:
                        log.warning(f"Step {step}: click failed: {e}")
                        self._dump_modal_state(f"click_fail_step{step}")
                        return False
                time.sleep(random.uniform(1.5, 2.5))

                if kind == "submit":
                    submitted = True
                    self.submitted_today += 1
                    log.info("Application Submitted")
                    break

                # Guard against being stuck on the same step. If we auto-filled
                # anything this iteration we made real progress — reset the
                # counter so the guard doesn't trip the moment the next page
                # also happens to show a "Next" button.
                if filled > 0:
                    same_kind_count = 0
                elif kind == last_kind:
                    same_kind_count += 1
                    if same_kind_count >= 3:
                        log.warning(f"Stuck on step kind='{kind}' x{same_kind_count}; bailing.")
                        self._dump_modal_state(f"stuck_{kind}")
                        self._dismiss_easy_apply_modal()
                        return False
                else:
                    same_kind_count = 0
                last_kind = kind

            if not submitted and not self.dry_run:
                log.warning("Exceeded MAX_STEPS without submission.")
                self._dump_modal_state("max_steps")
                self._dismiss_easy_apply_modal()

        except Exception as e:
            log.exception("send_resume failed")
            try:
                self._dump_modal_state("exception")
            except Exception:
                pass
            raise e

        return submitted

    def fill_invalids(self):
        # Historically this typed "3" into every unknown input and clicked "Yes"
        # on every radio — including visa sponsorship / clearance questions. That
        # ships garbage answers at scale and gets candidates auto-rejected.
        # Until we have a real per-question dispatcher, refuse to auto-answer and
        # let the caller skip the job instead.
        log.warning(
            "fill_invalids() invoked but auto-answering is disabled. "
            "Skipping this application; it has questions we can't answer confidently."
        )
        self.checked_invalid = True
        return

        try:
            select_inputs = self.browser.find_elements(By.CSS_SELECTOR, 'select[aria-required="true"]')

            for input in select_inputs:
                select_obj = Select(input)
                options = select_obj.options
                for option in options:
                    if "yes" in option.text.lower() or "native" in option.text.lower():
                        select_obj.select_by_visible_text(option.text)
                    else:
                        select_obj.select_by_index(0)
        except Exception as e:
            log.error('error doing select inputs', e)
                    
            
        # try:
        #     select_inputs = self.browser.find_elements(By.XPATH, '//select[contains(@class, "fb-dash-form-element__error-field"]')
        #     for input in select_inputs:
        #          input.select_by_value("Yes")
        # except:
        #     print('no select inputs found')

        # try:
        #     radio_inputs = self.browser.find_elements(By.XPATH, "//input[contains(@class, 'fb-form-element__checkbox']")
        #     for radio in radio_inputs:
        #         radio.click()
        # except:
        #     print('no radios found')

        


    def load_page(self, sleep=1):
        scroll_page = 0
        while scroll_page < 4000:
            self.browser.execute_script("window.scrollTo(0," + str(scroll_page) + " );")
            scroll_page += 200
            time.sleep(sleep)

        if sleep != 1:
            self.browser.execute_script("window.scrollTo(0,0);")
            time.sleep(sleep * 3)

        page = BeautifulSoup(self.browser.page_source, "lxml")
        return page

    def avoid_lock(self) -> None:
        # Prior version drove the real mouse and pressed Ctrl+Esc, hijacking the
        # user's keyboard mid-run. If you need to keep the machine awake, use
        # `caffeinate -di` (macOS) or `systemd-inhibit` (Linux) around the run.
        return

    def next_jobs_page(self, position, location, jobs_per_page):
        # f_AL=true: Easy Apply only (replaces legacy f_LF=f_AL).
        # f_TPR=r86400: posted in the last 24 hours.
        # f_WT=2: Remote work type.
        self.browser.get(
            "https://www.linkedin.com/jobs/search/?f_AL=true&f_TPR=r86400&f_WT=2"
            f"&keywords={position}{location}&start={jobs_per_page}"
            "&origin=JOB_SEARCH_PAGE_JOB_FILTER"
        )
        self.avoid_lock()
        log.info("Lock avoided.")
        self.load_page()
        return (self.browser, jobs_per_page)

    def finish_apply(self) -> None:
        self.browser.close()


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="LinkedIn Easy Apply bot")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="dry_run", action="store_true",
                      help="Walk the flow but never click Submit (default)")
    mode.add_argument("--live", dest="dry_run", action="store_false",
                      help="Actually submit applications")
    parser.set_defaults(dry_run=True)
    parser.add_argument("--daily-cap", type=int, default=25,
                        help="Max submissions per run (default 25)")
    parser.add_argument("--exit-after-login", action="store_true",
                        help="Log in, then exit — used to verify login flow")
    args = parser.parse_args()

    with open("./config.yaml", 'r') as stream:
        try:
            parameters = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise exc

    assert len(parameters['positions']) > 0
    assert len(parameters['locations']) > 0
    assert parameters['username'] is not None
    assert parameters['password'] is not None
    assert parameters['phone_number'] is not None

    if 'uploads' in parameters.keys() and type(parameters['uploads']) == list:
        raise Exception("uploads read from the config file appear to be in list format" +
                        " while should be dict. Try removing '-' from line containing" +
                        " filename & path")

    log.info({k: parameters[k] for k in parameters.keys() if k not in ['username', 'password']})

    output_filename: list = [f for f in parameters.get('output_filename', ['output.csv']) if f != None]
    output_filename: list = output_filename[0] if len(output_filename) > 0 else 'output.csv'
    blacklist = parameters.get('blacklist', [])
    blackListTitles = parameters.get('blackListTitles', [])

    uploads = {} if parameters.get('uploads', {}) == None else parameters.get('uploads', {})
    for key in uploads.keys():
        assert uploads[key] != None

    bot = EasyApplyBot(parameters['username'],
                       parameters['password'],
                       parameters['phone_number'],
                       uploads=uploads,
                       filename=output_filename,
                       blacklist=blacklist,
                       blackListTitles=blackListTitles,
                       dry_run=args.dry_run,
                       daily_cap=args.daily_cap,
                       )

    if args.exit_after_login:
        log.info(f"--exit-after-login set; current URL: {bot.browser.current_url}; exiting.")
        try:
            bot.browser.quit()
        except Exception:
            pass
        sys.exit(0)

    locations: list = [l for l in parameters['locations'] if l != None]
    positions: list = [p for p in parameters['positions'] if p != None]
    bot.start_apply(positions, locations)
