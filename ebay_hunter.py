# -*- coding: utf-8 -*-
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException, StaleElementReferenceException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import csv
import re
from datetime import datetime
import os
import traceback
import threading

# ========================
# GLOBAL WATCHDOG
# ========================


class Watchdog:
    """Global timeout watchdog - kills operations that take too long"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.last_activity = time.time()
        self.is_stuck = False

    def check(self, max_seconds=15):
        """Check if we've been stuck too long"""
        elapsed = time.time() - self.last_activity
        if elapsed > max_seconds:
            self.is_stuck = True
            return True
        return False

    def activity(self):
        """Record activity"""
        self.last_activity = time.time()
        self.is_stuck = False


watchdog = Watchdog()

# ========================
# TERMINAL COLORS
# ========================


class Colors:
    """ANSI color codes for terminal output"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    GRAY = '\033[90m'

    @staticmethod
    def success(text="✓"):
        return f"{Colors.GREEN}{text}{Colors.RESET}"

    @staticmethod
    def warning(text="⚠"):
        return f"{Colors.YELLOW}{text}{Colors.RESET}"

    @staticmethod
    def error(text="✗"):
        return f"{Colors.RED}{text}{Colors.RESET}"

    @staticmethod
    def info(text="ℹ"):
        return f"{Colors.CYAN}{text}{Colors.RESET}"

    @staticmethod
    def winner(text="★"):
        return f"{Colors.GREEN}{Colors.BOLD}{text}{Colors.RESET}"


# ========================
# CONFIGURATION
# ========================
INPUT_FILE = "product_keywords.txt"
OUTPUT_FILE = "ebay_keyword_results.csv"
STUCK_KEYWORDS_FILE = "stuck_keywords.txt"  # Track stuck/failed keywords
MIN_SALES_THRESHOLD = 5
WINNER_THRESHOLD = 10
SAVE_ALL_PRODUCTS = True

CHROME_PROFILE = "Profile 12"
RESTART_EVERY = 30
REQUEST_DELAY = 0.25
MAX_RETRIES = 2
PRODUCTS_PER_KEYWORD = 10

# Price filter configuration
MIN_PRICE = 8  # Minimum price filter in dollars

# Enhanced timeouts
PAGE_LOAD_TIMEOUT = 5
SEARCH_WAIT = 5
FILTER_WAIT = 8
FILTER_MAX_WAIT = 15
SCROLL_DELAY = 0.8
BUTTON_WAIT = 0.8
MAX_STUCK_TIME = 30
KEYWORD_STUCK_RETRY = 2  # Retry stuck keywords twice before skipping

# ========================
# ========================
# CSV SETUP - REINFORCED
# ========================

def setup_csv():
    """Create CSV file with headers if it doesn't exist"""
    if os.path.exists(OUTPUT_FILE):
        print(f"{Colors.success('✓')} Using existing file: {OUTPUT_FILE}")
        return True

    try:
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Keyword', 'Product URL', 'Price', 'January 2026 Sales',
                            'February 2026 Sales', 'Date Checked', 'Status'])
        print(f"{Colors.success('✓')} Created new file: {OUTPUT_FILE}")
        return True
    except Exception as e:
        print(f"{Colors.error('✗')} ERROR creating CSV file: {e}")
        return False


def get_processed_keywords():
    """Get keywords and their processed URLs from CSV - REINFORCED VERSION"""
    processed = {}
    if not os.path.exists(OUTPUT_FILE):
        return processed

    try:
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            # Read first line to check headers
            first_line = f.readline().strip()

            # Reset to beginning
            f.seek(0)

            # Check if file has proper headers
            if 'Keyword' in first_line and 'Product URL' in first_line:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        keyword = row['Keyword'].strip().lower()  # NORMALIZE: lowercase
                        url = row['Product URL'].strip()

                        if keyword and url:
                            if keyword not in processed:
                                processed[keyword] = set()
                            processed[keyword].add(url)
                    except KeyError:
                        continue
            else:
                # File exists but no proper headers - read as raw CSV
                reader = csv.reader(f)
                next(reader, None)  # Skip first line
                for row in reader:
                    if len(row) >= 2:
                        keyword = row[0].strip().lower()  # NORMALIZE: lowercase
                        url = row[1].strip()
                        if keyword and url:
                            if keyword not in processed:
                                processed[keyword] = set()
                            processed[keyword].add(url)

        print(f"{Colors.success('✓')} Loaded {sum(len(urls) for urls in processed.values())} processed products from CSV")
        
        # DEBUG: Show processed keywords count
        if processed:
            print(f"   {Colors.CYAN}→{Colors.RESET} Processed keywords: {len(processed)}")
            
    except Exception as e:
        print(f"{Colors.warning('⚠')} Error reading processed data: {e}")

    return processed


def get_completed_keywords(processed_data):
    """Get list of keywords that have been fully processed (10+ products) - REINFORCED"""
    completed = set()
    for keyword, urls in processed_data.items():
        if len(urls) >= PRODUCTS_PER_KEYWORD:
            completed.add(keyword.lower())  # NORMALIZE: lowercase
    
    # DEBUG: Show completed keywords
    if completed:
        print(f"   {Colors.GREEN}→{Colors.RESET} Completed keywords (≥{PRODUCTS_PER_KEYWORD} products): {len(completed)}")
    
    return completed


def is_keyword_completed(keyword, processed_data):
    """Check if a specific keyword has enough products - NEW FUNCTION"""
    keyword_normalized = keyword.strip().lower()
    urls = processed_data.get(keyword_normalized, set())
    return len(urls) >= PRODUCTS_PER_KEYWORD


def get_keyword_progress(keyword, processed_data):
    """Get progress for a keyword - NEW FUNCTION"""
    keyword_normalized = keyword.strip().lower()
    urls = processed_data.get(keyword_normalized, set())
    return len(urls)

def save_to_csv(result):
    """Append result to CSV file"""
    try:
        with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                result['keyword'],
                result['url'],
                result['price'],
                result['jan_sales'],
                result['feb_sales'],
                result['date_checked'],
                result.get('status', 'Success')
            ])
        watchdog.activity()
        return True
    except Exception as e:
        print(f"{Colors.error('✗')} Save error: {e}")
        return False


def load_stuck_keywords():
    """Load previously stuck keywords from file"""
    stuck = set()
    if os.path.exists(STUCK_KEYWORDS_FILE):
        try:
            with open(STUCK_KEYWORDS_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    keyword = line.strip()
                    if keyword and not keyword.startswith('#'):
                        stuck.add(keyword)
        except Exception as e:
            print(f"{Colors.warning('⚠')} Error reading stuck keywords: {e}")
    return stuck


def save_stuck_keyword(keyword, reason="Stuck during search"):
    """Save a stuck keyword to the stuck keywords file"""
    try:
        # Read existing stuck keywords
        existing = load_stuck_keywords()

        # Add new keyword if not already there
        if keyword not in existing:
            with open(STUCK_KEYWORDS_FILE, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{keyword}  # {reason} - {timestamp}\n")
            return True
    except Exception as e:
        print(f"{Colors.warning('⚠')} Error saving stuck keyword: {e}")
    return False

# ========================
# CHROME DRIVER SETUP
# ========================


def setup_chrome_driver():
    """Set up undetected Chrome driver with crash protection"""
    options = uc.ChromeOptions()
    options.add_argument(
        f"--user-data-dir=/Users/mac/Library/Application Support/Google/Chrome")
    options.add_argument(f"--profile-directory={CHROME_PROFILE}")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-logging")
    options.add_argument("--log-level=3")
    options.page_load_strategy = 'eager'

    try:
        driver = uc.Chrome(options=options, version_main=128,
                           driver_executable_path=None, use_subprocess=True)
        driver.implicitly_wait(1.5)
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)

        try:
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": driver.execute_script("return navigator.userAgent").replace('Headless', '')
            })
            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        except:
            pass

        watchdog.activity()
        return driver
    except Exception as e:
        print(f"{Colors.error('✗')} Driver setup failed: {e}")
        raise


def restart_browser_safe(driver):
    """Safely restart the browser with better error handling"""
    print("\n" + "="*70)
    print("💫 RESTARTING BROWSER (stuck prevention)")
    print("="*70)

    print(f"   {Colors.CYAN}→{Colors.RESET} Closing current browser instance...",
          end="", flush=True)
    try:
        driver.quit()
        time.sleep(0.3)
        print(f" {Colors.success('✓')}")
    except:
        print(f" {Colors.warning('⚠')} (already closed)")

    print(f"   {Colors.CYAN}→{Colors.RESET} Waiting for cleanup...",
          end="", flush=True)
    time.sleep(1.5)
    print(f" {Colors.success('✓')}")

    for attempt in range(3):
        try:
            print(
                f"   {Colors.CYAN}→{Colors.RESET} Starting new browser (attempt {attempt+1}/3)...", end="", flush=True)
            new_driver = setup_chrome_driver()
            print(f" {Colors.success('✓')}")
            print(f"   {Colors.GREEN}✓ Browser restart successful!{Colors.RESET}")
            print("="*70 + "\n")
            watchdog.reset()
            return new_driver
        except Exception as e:
            print(f" {Colors.error('✗')} FAILED")
            if attempt < 2:
                print(
                    f"   {Colors.CYAN}→{Colors.RESET} Retrying in 2 seconds...")
                time.sleep(2)
            else:
                print(
                    f"   {Colors.RED}✗ CRITICAL: Browser restart failed after 3 attempts{Colors.RESET}")
                print("="*70 + "\n")
                raise Exception("Browser restart failed permanently")


def is_driver_alive(driver):
    """Quick driver health check"""
    try:
        _ = driver.current_url
        watchdog.activity()
        return True
    except:
        return False

# ========================
# EBAY SEARCH & FILTER - ANTI-STUCK
# ========================


def apply_price_filter(driver):
    """Apply minimum price filter ($8) with anti-stuck protection"""
    try:
        watchdog.activity()
        start_time = time.time()
        max_attempt_time = 10
        
        print(f"   {Colors.CYAN}→{Colors.RESET} Applying price filter (min $8)...", end="", flush=True)
        
        # Try to find the minimum price input field
        min_price_selectors = [
            "//input[@aria-label='Minimum Value in $']",
            "//input[@placeholder='Min']",
            "//input[contains(@class, 'x-textrange__input--from')]",
            "//input[@name='_udlo']",
            "//*[@id='s0-51-12-6-2-2[0]-2-1-content-menu']//input[1]"  # Common eBay price filter
        ]
        
        price_input = None
        for selector in min_price_selectors:
            if time.time() - start_time > max_attempt_time or watchdog.check(MAX_STUCK_TIME):
                print(f" {Colors.warning('⚠')} (timeout)")
                return False
                
            try:
                price_input = driver.find_element(By.XPATH, selector)
                if price_input.is_displayed():
                    break
            except:
                continue
        
        if not price_input:
            print(f" {Colors.warning('⚠')} (not found)")
            return False
        
        # Clear and enter minimum price
        try:
            driver.execute_script("arguments[0].scrollIntoView(true);", price_input)
            time.sleep(0.2)
            price_input.clear()
            price_input.send_keys(str(MIN_PRICE))
            watchdog.activity()
            time.sleep(0.3)
            
            # Try to submit the price filter
            submit_selectors = [
                "//button[contains(text(), 'Submit price range')]",
                "//button[@aria-label='Submit price range']",
                "//button[contains(@class, 'x-textrange__input-btn')]"
            ]
            
            for selector in submit_selectors:
                try:
                    submit_btn = driver.find_element(By.XPATH, selector)
                    if submit_btn.is_displayed() and submit_btn.is_enabled():
                        driver.execute_script("arguments[0].click();", submit_btn)
                        watchdog.activity()
                        time.sleep(BUTTON_WAIT)
                        print(f" {Colors.success('✓')}")
                        return True
                except:
                    continue
            
            # If no submit button found, try pressing Enter
            price_input.send_keys(Keys.RETURN)
            watchdog.activity()
            time.sleep(BUTTON_WAIT)
            print(f" {Colors.success('✓')}")
            return True
            
        except Exception as e:
            print(f" {Colors.warning('⚠')} (error: {str(e)[:30]})")
            return False
            
    except Exception:
        print(f" {Colors.warning('⚠')} (failed)")
        return False


def search_ebay_keyword(driver, keyword, retry=0):
    """Search eBay for a keyword with anti-stuck protection"""
    try:
        watchdog.reset()

        if not is_driver_alive(driver):
            return False

        # Navigate to eBay with timeout
        start = time.time()
        try:
            driver.get("https://www.ebay.com")
            watchdog.activity()
            time.sleep(SEARCH_WAIT)
        except TimeoutException:
            if time.time() - start > MAX_STUCK_TIME:
                print(
                    f"   {Colors.warning('⚠')} Navigation stuck, forcing stop...")
            try:
                driver.execute_script("window.stop();")
                watchdog.activity()
            except:
                pass

        # Check if stuck during navigation
        if watchdog.check(MAX_STUCK_TIME):
            print(
                f"   {Colors.error('✗')} STUCK during navigation - needs restart")
            return False

        # Search with timeout
        start = time.time()
        try:
            search_box = WebDriverWait(driver, 6).until(
                EC.presence_of_element_located((By.ID, "gh-ac"))
            )
            search_box.clear()
            search_box.send_keys(keyword)
            search_box.send_keys(Keys.RETURN)
            watchdog.activity()
            time.sleep(SEARCH_WAIT)
        except TimeoutException:
            if time.time() - start > MAX_STUCK_TIME or watchdog.check(MAX_STUCK_TIME):
                print(
                    f"   {Colors.error('✗')} STUCK on search box - needs restart")
                return False

            if retry < MAX_RETRIES:
                print(f"   {Colors.warning('⚠')} Search timeout, retrying...")
                time.sleep(1)
                return search_ebay_keyword(driver, keyword, retry + 1)
            print(
                f"   {Colors.error('✗')} Search failed after {MAX_RETRIES} attempts")
            return False
        except Exception as e:
            print(f"   {Colors.error('✗')} Search error: {e}")
            return False

        # Apply price filter FIRST
        price_ok = apply_price_filter(driver)
        if price_ok:
            time.sleep(FILTER_WAIT)

        # Apply filters with strict timeout
        print(
            f"   {Colors.CYAN}→{Colors.RESET} Applying US Only filter...", end="", flush=True)
        us_start = time.time()
        us_ok = apply_us_only_filter_safe(driver)

        # Check if stuck on US filter
        if time.time() - us_start > FILTER_MAX_WAIT or watchdog.check(MAX_STUCK_TIME):
            print(f" {Colors.error('✗ STUCK - needs restart')}")
            return False

        if us_ok:
            print(f" {Colors.success('✓')}")
        else:
            print(f" {Colors.warning('⚠')} (skipped)")

        print(
            f"   {Colors.CYAN}→{Colors.RESET} Applying Unbranded filter...", end="", flush=True)
        unbranded_start = time.time()
        unbranded_ok = apply_unbranded_filter_safe(driver)

        # Check if stuck on Unbranded filter
        if time.time() - unbranded_start > FILTER_MAX_WAIT or watchdog.check(MAX_STUCK_TIME):
            print(f" {Colors.error('✗ STUCK - needs restart')}")
            return False

        if unbranded_ok:
            print(f" {Colors.success('✓')}")
        else:
            print(f" {Colors.warning('⚠')} (skipped)")

        watchdog.activity()
        time.sleep(FILTER_WAIT)
        return True

    except Exception as e:
        print(f"   {Colors.error('✗')} Keyword search error: {e}")
        return False


def apply_us_only_filter_safe(driver):
    """Apply US Only filter with strict anti-stuck timeout - checks Recently used filters first"""
    start_time = time.time()

    try:
        # PRIORITY 1: Check "Recently used filters" section first (fastest)
        recently_used_selectors = [
            "//h3[contains(text(), 'Recently used filters')]//following::span[contains(text(), 'US Only')]",
            "//div[contains(@class, 'recently') or contains(text(), 'Recently used')]//following::span[contains(text(), 'US Only')]",
            "//section[contains(@aria-label, 'Recently')]//span[contains(text(), 'US Only')]"
        ]
        
        for selector in recently_used_selectors:
            if time.time() - start_time > FILTER_MAX_WAIT or watchdog.check(MAX_STUCK_TIME):
                return False
            
            try:
                element = driver.find_element(By.XPATH, selector)
                if element.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView(true);", element)
                    time.sleep(0.1)
                    driver.execute_script("arguments[0].click();", element)
                    watchdog.activity()
                    time.sleep(BUTTON_WAIT)
                    return True
            except:
                continue
        
        # PRIORITY 2: Standard selectors (fallback)
        selectors = [
            "//span[contains(text(), 'US Only')]",
            "//a[contains(text(), 'US Only')]",
            "//div[contains(text(), 'US Only')]"
        ]

        while time.time() - start_time < FILTER_MAX_WAIT:
            if watchdog.check(MAX_STUCK_TIME):
                return False

            for selector in selectors:
                try:
                    element = driver.find_element(By.XPATH, selector)
                    driver.execute_script(
                        "arguments[0].scrollIntoView(true);", element)
                    time.sleep(0.1)
                    driver.execute_script("arguments[0].click();", element)
                    watchdog.activity()
                    time.sleep(BUTTON_WAIT)
                    return True
                except (NoSuchElementException, StaleElementReferenceException):
                    continue

            watchdog.activity()
            time.sleep(0.3)

        return False
    except Exception:
        return False


def apply_unbranded_filter_safe(driver):
    """Apply Unbranded filter - checks Recently used filters first, then tries expansion"""
    start_time = time.time()
    max_attempt_time = 8  # Only try for 8 seconds total

    try:
        # PRIORITY 1: Check "Recently used filters" section FIRST (fastest & most reliable)
        recently_used_selectors = [
            "//h3[contains(text(), 'Recently used filters')]//following::span[contains(text(), 'Unbranded')]",
            "//div[contains(@class, 'recently') or contains(text(), 'Recently used')]//following::span[contains(text(), 'Unbranded')]",
            "//section[contains(@aria-label, 'Recently')]//span[contains(text(), 'Unbranded')]",
            "//h3[text()='Recently used filters']/following::*[contains(text(), 'Unbranded')]"
        ]
        
        for selector in recently_used_selectors:
            if time.time() - start_time > max_attempt_time or watchdog.check(MAX_STUCK_TIME):
                return False
            
            try:
                element = driver.find_element(By.XPATH, selector)
                if element.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView(true);", element)
                    time.sleep(0.1)
                    driver.execute_script("arguments[0].click();", element)
                    watchdog.activity()
                    time.sleep(BUTTON_WAIT)
                    return True
            except:
                continue
        
        # PRIORITY 2: Try direct selection (Unbranded is already visible in main filters)
        unbranded_selectors = [
            "//span[contains(text(), 'Unbranded')]",
            "//a[contains(text(), 'Unbranded')]",
            "//input[@aria-label='Unbranded']",
            "//label[contains(text(), 'Unbranded')]"
        ]

        # Quick first pass - try direct selection
        for selector in unbranded_selectors:
            if time.time() - start_time > max_attempt_time or watchdog.check(MAX_STUCK_TIME):
                return False

            try:
                element = driver.find_element(By.XPATH, selector)
                if element.is_displayed():
                    driver.execute_script(
                        "arguments[0].scrollIntoView(true);", element)
                    time.sleep(0.1)
                    driver.execute_script("arguments[0].click();", element)
                    watchdog.activity()
                    time.sleep(BUTTON_WAIT)
                    return True
            except:
                continue

        # FALLBACK: Try expanding Brand section (but limit time)
        if time.time() - start_time < max_attempt_time and not watchdog.check(MAX_STUCK_TIME):
            brand_expand_selectors = [
                "//h3[contains(text(), 'Brand')]//parent::button",
                "//button[contains(@aria-label, 'Brand')]",
                "//div[contains(@class, 'x-refine__main__list')]//button[.//span[contains(text(), 'Brand')]]",
                "//span[contains(text(), 'Brand')]//ancestor::button"
            ]

            for selector in brand_expand_selectors:
                if time.time() - start_time > max_attempt_time or watchdog.check(MAX_STUCK_TIME):
                    return False

                try:
                    brand_button = driver.find_element(By.XPATH, selector)
                    driver.execute_script(
                        "arguments[0].scrollIntoView(true);", brand_button)
                    time.sleep(0.2)
                    driver.execute_script("arguments[0].click();", brand_button)
                    watchdog.activity()
                    time.sleep(0.5)

                    # Quick check for Unbranded after expanding
                    for unbranded_selector in unbranded_selectors:
                        if time.time() - start_time > max_attempt_time or watchdog.check(MAX_STUCK_TIME):
                            return False

                        try:
                            element = driver.find_element(By.XPATH, unbranded_selector)
                            if element.is_displayed():
                                driver.execute_script(
                                    "arguments[0].scrollIntoView(true);", element)
                                time.sleep(0.1)
                                driver.execute_script("arguments[0].click();", element)
                                watchdog.activity()
                                time.sleep(BUTTON_WAIT)
                                return True
                        except:
                            continue
                    
                    # If we expanded Brand but didn't find Unbranded quickly, give up
                    break
                except:
                    continue

        # Don't try Brand Type at all - it opens too many options and causes timeout
        # Just return False and let the search continue without Unbranded filter
        return False
        
    except Exception:
        return False


def extract_product_urls(driver, max_products=10):
    """Extract product URLs with anti-stuck protection"""
    try:
        watchdog.activity()

        if not is_driver_alive(driver):
            return []

        start = time.time()
        try:
            driver.execute_script("window.scrollTo(0, 600);")
            time.sleep(SCROLL_DELAY)
            driver.execute_script("window.scrollTo(0, 1200);")
            time.sleep(SCROLL_DELAY)
            driver.execute_script("window.scrollTo(0, 0);")
            watchdog.activity()
            time.sleep(0.2)
        except:
            pass

        if time.time() - start > MAX_STUCK_TIME or watchdog.check(MAX_STUCK_TIME):
            print(f"   {Colors.warning('⚠')} Stuck during scroll, continuing...")
            return []

        js_extract = """
        const links = document.querySelectorAll('a[href*="/itm/"]');
        const urls = new Set();
        
        for (let link of links) {
            const match = link.href.match(/\\/itm\\/(\\d+)/);
            if (match && match[1] && match[1].length >= 10) {
                urls.add(`https://www.ebay.com/itm/${match[1]}`);
                if (urls.size >= arguments[0]) break;
            }
        }
        return Array.from(urls);
        """

        urls = driver.execute_script(js_extract, max_products)
        watchdog.activity()
        return urls[:max_products]

    except Exception:
        return []

# ========================
# PRICE & HISTORY
# ========================


def extract_price(driver):
    """Extract product price from eBay listing"""
    try:
        watchdog.activity()

        if not is_driver_alive(driver):
            return "N/A"

        js_price = """
        const priceEl = document.querySelector('.x-price-primary .ux-textspans, [itemprop="price"], .x-price-primary');
        if (priceEl) {
            const match = priceEl.textContent.match(/[\\$]?\\s*([\\d,]+\\.?\\d*)/);
            if (match) return match[1].replace(/,/g, '');
        }
        
        const bodyText = document.body.innerText;
        const priceMatch = bodyText.match(/US \\$([\\d,]+\\.?\\d*)/);
        if (priceMatch) return priceMatch[1].replace(/,/g, '');
        
        const altMatch = bodyText.match(/\\$([\\d,]+\\.?\\d*)/);
        if (altMatch) return altMatch[1].replace(/,/g, '');
        
        return null;
        """

        js_result = driver.execute_script(js_price)
        watchdog.activity()

        if js_result:
            return f"${js_result}"

        return "N/A"
    except Exception:
        return "N/A"


def wait_for_extension_button(driver, max_wait=2.0):
    """Wait for extension button with timeout"""
    start_time = time.time()

    while time.time() - start_time < max_wait:
        if watchdog.check(MAX_STUCK_TIME):
            return None

        try:
            if not is_driver_alive(driver):
                return None

            buttons = driver.find_elements(
                By.XPATH, "//*[contains(text(), 'View Sold History')]")

            for button in buttons:
                try:
                    if button.is_displayed() and button.is_enabled():
                        watchdog.activity()
                        return button
                except:
                    continue
        except:
            pass

        watchdog.activity()
        time.sleep(0.15)

    return None


def click_sold_history_button(driver):
    """Click sold history button with anti-stuck protection"""
    try:
        watchdog.activity()

        if not is_driver_alive(driver):
            return False, None

        original_window = driver.current_window_handle
        original_handles = set(driver.window_handles)

        button = wait_for_extension_button(driver)

        if not button:
            return False, None

        try:
            driver.execute_script("arguments[0].scrollIntoView(true);", button)
            time.sleep(0.1)
            driver.execute_script("arguments[0].click();", button)
            watchdog.activity()
        except Exception:
            try:
                button.click()
                watchdog.activity()
            except:
                return False, None

        start = time.time()
        for i in range(10):
            if time.time() - start > MAX_STUCK_TIME or watchdog.check(MAX_STUCK_TIME):
                return False, None

            time.sleep(0.25)
            try:
                current_handles = set(driver.window_handles)
                new_handles = current_handles - original_handles

                if new_handles:
                    new_window = new_handles.pop()
                    driver.switch_to.window(new_window)
                    watchdog.activity()
                    return True, original_window
            except Exception:
                pass

        return False, None

    except Exception:
        return False, None


def parse_sold_history(driver):
    """Parse sold history with anti-stuck timeout - Updated for Jan and Feb 2026"""
    try:
        watchdog.activity()

        if not is_driver_alive(driver):
            return {"Jan 2026": 0, "Feb 2026": 0}

        start = time.time()
        for i in range(6):
            if time.time() - start > MAX_STUCK_TIME or watchdog.check(MAX_STUCK_TIME):
                return {"Jan 2026": 0, "Feb 2026": 0}

            try:
                page_text = driver.execute_script(
                    "return document.body.innerText;")

                if len(page_text) > 100:
                    jan_count = page_text.count("Jan 2026")
                    feb_count = page_text.count("Feb 2026")
                    watchdog.activity()
                    return {"Jan 2026": jan_count, "Feb 2026": feb_count}
            except Exception:
                pass

            watchdog.activity()
            time.sleep(0.15)

        return {"Jan 2026": 0, "Feb 2026": 0}
    except:
        return {"Jan 2026": 0, "Feb 2026": 0}


def close_extra_tabs(driver, original_window):
    """Close extra tabs quickly"""
    try:
        watchdog.activity()

        if not is_driver_alive(driver):
            return

        all_windows = driver.window_handles

        for window in all_windows:
            if window != original_window:
                try:
                    driver.switch_to.window(window)
                    driver.close()
                    watchdog.activity()
                except:
                    pass

        try:
            driver.switch_to.window(original_window)
            watchdog.activity()
        except:
            if driver.window_handles:
                driver.switch_to.window(driver.window_handles[0])
                watchdog.activity()
    except:
        pass

# ========================
# PROCESS PRODUCT
# ========================


def process_product(driver, keyword, url, product_index, retry_count=0):
    """Process single product with anti-stuck protection"""
    try:
        watchdog.activity()

        if not is_driver_alive(driver):
            return None, False

        if not url.startswith('https://www.ebay.com/itm/'):
            return None, True

        item_id = url.split('/')[-1].split('?')[0]
        if not item_id.isdigit() or len(item_id) < 10:
            return None, True

        start = time.time()
        try:
            driver.get(url)
            watchdog.activity()
        except TimeoutException:
            if time.time() - start > MAX_STUCK_TIME or watchdog.check(MAX_STUCK_TIME):
                print(
                    f"      [{product_index}/{PRODUCTS_PER_KEYWORD}] STUCK on navigation - needs restart")
                return None, False

            try:
                driver.execute_script("window.stop();")
                watchdog.activity()
            except:
                pass

            if retry_count < MAX_RETRIES:
                time.sleep(0.5)
                return process_product(driver, keyword, url, product_index, retry_count + 1)
            return None, True
        except WebDriverException:
            return None, False

        loaded = False
        load_start = time.time()
        for i in range(4):
            if time.time() - load_start > MAX_STUCK_TIME or watchdog.check(MAX_STUCK_TIME):
                print(
                    f"      [{product_index}/{PRODUCTS_PER_KEYWORD}] STUCK waiting for page - needs restart")
                return None, False

            time.sleep(0.2)
            try:
                if is_driver_alive(driver):
                    body_length = driver.execute_script(
                        "return document.body.innerText.length;")
                    if body_length > 100:
                        loaded = True
                        watchdog.activity()
                        break
            except Exception:
                pass

        if not loaded:
            if retry_count < MAX_RETRIES:
                time.sleep(0.5)
                return process_product(driver, keyword, url, product_index, retry_count + 1)
            return None, True

        price = extract_price(driver)
        success, original_window = click_sold_history_button(driver)

        if not success:
            return None, True

        sales_count = parse_sold_history(driver)
        close_extra_tabs(driver, original_window)

        result = {
            'keyword': keyword,
            'url': url,
            'price': price,
            'jan_sales': sales_count["Jan 2026"],
            'feb_sales': sales_count["Feb 2026"],
            'date_checked': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'status': 'Success'
        }

        jan = sales_count["Jan 2026"]
        feb = sales_count["Feb 2026"]
        total = jan + feb

        print(
            f"      [{product_index}/{PRODUCTS_PER_KEYWORD}]       [{item_id}]... ", end="", flush=True)

        if total >= WINNER_THRESHOLD:
            print(f"{Colors.winner('WINNER!')} {Colors.GREEN}🎯{Colors.RESET} {price} | Jan:{jan} Feb:{feb} Total:{total} {Colors.success('✓')}")
            watchdog.activity()
            return result, True
        elif jan >= MIN_SALES_THRESHOLD or feb >= MIN_SALES_THRESHOLD:
            print(
                f"{Colors.CYAN}Good!{Colors.RESET} 💰 {price} | Jan:{jan} Feb:{feb} Total:{total}")
            watchdog.activity()
            return result, True
        else:
            if SAVE_ALL_PRODUCTS:
                print(
                    f"{Colors.GRAY}saved{Colors.RESET} 💾 {price} | Jan:{jan} Feb:{feb} Total:{total}")
                watchdog.activity()
                return result, True
            print(f"{Colors.GRAY}skip{Colors.RESET} ⏭️ {price} | Jan:{jan} Feb:{feb}")
            return None, True

    except WebDriverException:
        return None, False
    except Exception as e:
        return None, True

# ========================
# PROCESS KEYWORD
# ========================


def process_keyword(driver, keyword, processed_urls, stuck_count=0):
    """Process keyword with comprehensive anti-stuck protection and retry logic"""
    print(f"\n{'='*70}")
    print(f"🎯 {Colors.BOLD}KEYWORD:{Colors.RESET} {keyword}")
    if stuck_count > 0:
        print(
            f"   {Colors.YELLOW}⚠ Retry attempt {stuck_count}/{KEYWORD_STUCK_RETRY}{Colors.RESET}")
    print(f"{'='*70}")

    try:
        watchdog.reset()

        if not is_driver_alive(driver):
            print(f"   {Colors.error('✗')} Browser not responding")
            return 0, False, stuck_count

        # Search with timeout
        if not search_ebay_keyword(driver, keyword):
            if watchdog.is_stuck:
                if stuck_count < KEYWORD_STUCK_RETRY:
                    print(
                        f"   {Colors.warning('⚠')} STUCK during search - will retry after browser restart")
                    return 0, False, stuck_count + 1
                else:
                    print(
                        f"   {Colors.error('✗')} STUCK {KEYWORD_STUCK_RETRY} times - skipping keyword")
                    return 0, True, 0
            print(f"   {Colors.error('✗')} Search failed, moving to next keyword")
            return 0, True, 0

        print(f"   📦 Extracting top {PRODUCTS_PER_KEYWORD} products...")

        # Extract URLs
        urls = extract_product_urls(driver, PRODUCTS_PER_KEYWORD)

        if not urls:
            print(
                f"   {Colors.warning('⚠')} No products found, moving to next keyword")
            return 0, True, 0

        print(f"   🔗 Sample URLs extracted:")
        for i, url in enumerate(urls[:3], 1):
            print(f"      {i}. {url}")

        # Filter new URLs - CHECK CSV TO AVOID DUPLICATES
        keyword_processed = processed_urls.get(keyword, set())
        new_urls = [url for url in urls if url not in keyword_processed]

        if not new_urls:
            print(
                f"   {Colors.success('✓')} All {len(urls)} products already processed")
            return 0, True, 0

        print(f"   {Colors.success('✓')} Found {len(urls)} products ({len(new_urls)} new, {len(urls) - len(new_urls)} skipped)")
        print(f"   🏃 Starting to process...")

        # Process products
        saved_count = 0
        for i, url in enumerate(new_urls, 1):
            result, browser_ok = process_product(driver, keyword, url, i)

            if not browser_ok:
                print(
                    f"   {Colors.error('✗')} Browser crashed during product processing")
                return saved_count, False, stuck_count

            if result:
                save_to_csv(result)
                saved_count += 1
                keyword_processed.add(url)

            time.sleep(REQUEST_DELAY)

        print(
            f"   {Colors.GREEN}✓ Keyword complete: {saved_count} products saved{Colors.RESET}")
        return saved_count, True, 0

    except Exception as e:
        print(f"   {Colors.error('✗')} Keyword processing error: {e}")
        return 0, True, 0

# ========================
# MAIN
# ========================


def main():
    print(f"{Colors.BOLD}🚀 eBay KEYWORD Hunter - NEVER-STUCK VERSION (with $8 min price){Colors.RESET}")
    print("="*70)
    print(f"⚙️  Settings:")
    print(f"   • Products per keyword: {PRODUCTS_PER_KEYWORD}")
    print(f"   • Request delay: {REQUEST_DELAY}s")
    print(f"   • Browser restart: every {RESTART_EVERY} products")
    print(f"   • Winner threshold: {WINNER_THRESHOLD}+ total sales")
    print(f"   • Min sales: {MIN_SALES_THRESHOLD}")
    print(f"   • Min price filter: ${MIN_PRICE}")
    print(f"   • Save all: {SAVE_ALL_PRODUCTS}")
    print(f"   • Max stuck time: {MAX_STUCK_TIME}s (auto-restart)")
    print(f"   • Keyword retry on stuck: {KEYWORD_STUCK_RETRY} times")
    print(f"   • Sales months: January & February 2026")
    print("="*70)

    # Initialize session stuck keywords tracker
    session_stuck_keywords = set()

    # Load keywords from file
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            # NORMALIZE: strip whitespace and convert to lowercase
            all_keywords = [line.strip() for line in f
                            if line.strip() and not line.startswith('#')]

        if not all_keywords:
            print(f"{Colors.error('✗')} No keywords in {INPUT_FILE}")
            return

        # Remove duplicates while preserving order
        seen = set()
        unique_keywords = []
        for kw in all_keywords:
            kw_normalized = kw.lower()
            if kw_normalized not in seen:
                seen.add(kw_normalized)
                unique_keywords.append(kw)
        
        all_keywords = unique_keywords
        print(f"{Colors.success('✓')} Loaded {len(all_keywords)} unique keywords from file")

    except FileNotFoundError:
        print(f"{Colors.error('✗')} {INPUT_FILE} not found!")
        return

    # Setup CSV
    if not setup_csv():
        return

    # Get processed data - REINFORCED CHECK
    print(f"\n{Colors.CYAN}🔍 Checking processed data...{Colors.RESET}")
    processed_data = get_processed_keywords()
    completed_keywords = get_completed_keywords(processed_data)

    # Filter keywords - TRIPLE CHECK with normalization
    keywords_to_process = []
    for kw in all_keywords:
        kw_normalized = kw.lower()
        
        # Check 1: Not in completed set
        if kw_normalized in completed_keywords:
            continue
            
        # Check 2: Not enough products (double-check)
        if is_keyword_completed(kw, processed_data):
            continue
            
        # Check 3: Count products manually
        product_count = get_keyword_progress(kw, processed_data)
        if product_count >= PRODUCTS_PER_KEYWORD:
            continue
        
        keywords_to_process.append(kw)

    if not keywords_to_process:
        print(f"\n{Colors.success('✓')} All keywords already processed!")
        print(f"{Colors.GREEN}All {len(all_keywords)} keywords have {PRODUCTS_PER_KEYWORD}+ products in CSV{Colors.RESET}")
        return

    # Show summary
    skipped = len(all_keywords) - len(keywords_to_process)
    print(f"\n📊 {Colors.BOLD}CSV Summary:{Colors.RESET}")
    print(f"   • Total unique keywords in file: {len(all_keywords)}")
    print(f"   • Already completed: {skipped} ({skipped*100//len(all_keywords) if all_keywords else 0}%)")
    print(f"   • Remaining to process: {len(keywords_to_process)}")

    if keywords_to_process:
        print(f"\n📋 {Colors.BOLD}Next keywords to process:{Colors.RESET}")
        for i, kw in enumerate(keywords_to_process[:5], 1):
            existing = get_keyword_progress(kw, processed_data)
            if existing > 0:
                print(f"   {i}. {kw} ({existing}/{PRODUCTS_PER_KEYWORD} products)")
            else:
                print(f"   {i}. {kw} (new)")

        if len(keywords_to_process) > 5:
            print(f"   ... and {len(keywords_to_process) - 5} more")

    # Launch browser
    print(f"\n🌐 Launching Chrome...")
    driver = setup_chrome_driver()

    print(f"\n{Colors.YELLOW}⏸️  Please LOGIN to eBay now{Colors.RESET}")
    print(f"{Colors.YELLOW}⚠️  Ensure 'View Sold History' extension is active!{Colors.RESET}")
    input(f"{Colors.GREEN}✓ Press ENTER when ready...{Colors.RESET}\n")

    print("🏃 Starting...\n")

    # Process keywords
    total_saved = 0
    processed_count = 0
    browser_restart_counter = 0
    start_time = time.time()
    crash_count = 0
    keyword_stuck_counts = {}

    try:
        i = 0
        while i < len(keywords_to_process):
            keyword = keywords_to_process[i]
            
            # FINAL CHECK: Skip if already completed (real-time check)
            # Reload processed data to catch any concurrent updates
            if i % 5 == 0:  # Refresh every 5 keywords
                processed_data = get_processed_keywords()
            
            if is_keyword_completed(keyword, processed_data):
                print(f"\n{'='*70}")
                print(f"⏭️  {Colors.YELLOW}SKIPPING:{Colors.RESET} {keyword}")
                print(f"   {Colors.GREEN}✓ Already has {get_keyword_progress(keyword, processed_data)}/{PRODUCTS_PER_KEYWORD} products{Colors.RESET}")
                print(f"{'='*70}")
                i += 1
                continue

            # Health check
            if not is_driver_alive(driver):
                try:
                    driver = restart_browser_safe(driver)
                    browser_restart_counter = 0
                    crash_count += 1
                    continue
                except Exception as e:
                    break

            # Get stuck count for this keyword
            stuck_count = keyword_stuck_counts.get(keyword, 0)

            # Process keyword with retry logic
            saved, success, new_stuck_count = process_keyword(
                driver, keyword, processed_data, stuck_count)

            if not success:
                # Update stuck count
                keyword_stuck_counts[keyword] = new_stuck_count

                # Restart browser
                try:
                    driver = restart_browser_safe(driver)
                    browser_restart_counter = 0
                    crash_count += 1

                    # If stuck count exceeded, move to next keyword
                    if new_stuck_count == 0:
                        save_stuck_keyword(keyword, "Stuck during search - max retries exceeded")
                        session_stuck_keywords.add(keyword)
                        i += 1
                        if keyword in keyword_stuck_counts:
                            del keyword_stuck_counts[keyword]
                    continue
                except Exception as e:
                    break
            else:
                # Success - clear stuck count and move to next
                if keyword in keyword_stuck_counts:
                    del keyword_stuck_counts[keyword]
                total_saved += saved
                processed_count += 1
                i += 1

            # Periodic restart
            browser_restart_counter += PRODUCTS_PER_KEYWORD
            if browser_restart_counter >= RESTART_EVERY:
                try:
                    driver = restart_browser_safe(driver)
                    browser_restart_counter = 0
                except Exception as e:
                    break

            # Progress update
            if i % 10 == 0 and i > 0:
                elapsed = time.time() - start_time
                rate = i / (elapsed / 60) if elapsed > 0 else 0
                eta_min = (len(keywords_to_process) - i) / rate if rate > 0 else 0

                print(f"\n{'='*70}")
                print(f"📊 {Colors.BOLD}PROGRESS REPORT{Colors.RESET}")
                print(f"{'='*70}")
                print(f"   Keywords: {i}/{len(keywords_to_process)} ({i*100//len(keywords_to_process)}%)")
                print(f"   Saved: {total_saved} | Crashes: {crash_count}")
                print(f"   Speed: {rate:.1f} kw/min | Time: {elapsed/60:.1f}m | ETA: {eta_min:.0f}m")
                print(f"{'='*70}\n")

    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}⚠️  STOPPED BY USER{Colors.RESET}")
    except Exception as e:
        print(f"\n\n{Colors.RED}✗ CRITICAL ERROR: {e}{Colors.RESET}")
        traceback.print_exc()
    finally:
        try:
            driver.quit()
        except:
            pass

        elapsed = time.time() - start_time

        print("\n" + "="*70)
        print(f"{Colors.GREEN}✓ SESSION COMPLETE!{Colors.RESET}")
        print(f"   Time: {elapsed/60:.1f}m ({elapsed/3600:.1f}h)")
        print(f"   Keywords: {processed_count}/{len(keywords_to_process)}")
        print(f"   Products saved: {total_saved}")
        print(f"   Crashes: {crash_count}")
        if processed_count > 0:
            print(f"   Speed: {processed_count/(elapsed/60):.1f} kw/min")
        print(f"   Results: {OUTPUT_FILE}")
        print("="*70)

        # Show stuck keywords from this session
        if session_stuck_keywords:
            print(f"\n{Colors.YELLOW}⚠️  STUCK/FAILED KEYWORDS THIS SESSION:{Colors.RESET}")
            print("="*70)
            for i, kw in enumerate(session_stuck_keywords, 1):
                print(f"   {i}. {kw}")
            print(f"\n{Colors.CYAN}💡 These keywords have been saved to: {STUCK_KEYWORDS_FILE}{Colors.RESET}")
            print(f"{Colors.CYAN}💡 They will be shown in every session until processed{Colors.RESET}")
            print("="*70)

        # Show all accumulated stuck keywords
        all_stuck = load_stuck_keywords()
        if all_stuck:
            print(f"\n{Colors.RED}📋 ALL STUCK KEYWORDS (from all sessions):{Colors.RESET}")
            print("="*70)
            for i, kw in enumerate(sorted(all_stuck), 1):
                print(f"   {i}. {kw}")
            print(f"\n{Colors.YELLOW}⚠️  Total stuck keywords: {len(all_stuck)}{Colors.RESET}")
            print(f"{Colors.CYAN}💡 To retry these keywords:{Colors.RESET}")
            print(f"   1. Add them back to '{INPUT_FILE}'")
            print(f"   2. Delete '{STUCK_KEYWORDS_FILE}' (or remove specific lines)")
            print(f"   3. Run the script again")
            print("="*70)

        if processed_count < len(keywords_to_process):
            print(f"\n{Colors.CYAN}💡 Run script again to continue!{Colors.RESET}")


if __name__ == "__main__":
    main()
