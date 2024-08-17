import logging
import os
import re
import requests
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchWindowException, TimeoutException

# Configure logging
logging.basicConfig(format="[%(levelname)s] of-scraper: %(message)s", level=logging.INFO)
logging.info("Starting...")

def sanitize_filename(filename):
    """Sanitize filename by removing illegal characters, converting to lowercase, and replacing spaces with underscores."""
    # Remove illegal characters
    sanitized = re.sub(r'[<>:"/\\|?*\n\r\t]', '', filename)
    # Replace spaces with underscores
    sanitized = sanitized.replace(' ', '_')
    # Convert to lowercase
    sanitized = sanitized.lower()
    return sanitized

def get_cookie_header(cookies):
    """Generate cookie header for requests."""
    return {"Cookie": "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies)}

def configure_webdriver():
    """Configure and return the Selenium WebDriver."""
    options = Options()
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument(f"user-data-dir={os.getcwd()}/chrome-profile")
    return webdriver.Chrome(service=Service(), options=options)

def download_file(url, directory, headers=None):
    """Download a file from a URL and save it to a directory."""
    session = requests.Session()

    try:
        response = session.get(url, headers=headers, stream=True)
        response.raise_for_status()
        filename = sanitize_filename(os.path.basename(urlparse(url).path))
        file_path = os.path.join(directory, filename)
        with open(file_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)
        logging.info(f"Downloaded {filename}")
    except (requests.HTTPError, Exception) as e:
        logging.error(f"Failed to download {url}: {e}")

def process_album(driver, album_url, headers):
    """Process an album by extracting and downloading images and videos."""
    driver.execute_script(f"window.open('{album_url}', '_blank');")
    logging.info(f"Opening album: {album_url}")
    driver.switch_to.window(driver.window_handles[-1])
    try:
        
        title = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//h1"))).text
        logging.info(f"Album title: {title}")
        sanatized_title = sanitize_filename(title)
        os.makedirs(sanatized_title, exist_ok=True)

        # Gather image URLs
        img_elements = WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.XPATH, "//div[@class='img']")))
        for img in img_elements:
            data_src = img.get_attribute('data-src')
            download_file(data_src, sanatized_title, headers)

        # Gather video URLs
        video_elements = WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.XPATH, "//source[@type='video/mp4']")))
        for video in video_elements:
            src = video.get_attribute('src')
            download_file(src, sanatized_title, headers)

    except TimeoutException:
        logging.warning(f"Timeout while processing album: {album_url}")
    except Exception as e:
        logging.error(f"Error while processing album {album_url}: {e}")
    finally:
        driver.close()
        driver.switch_to.window(driver.window_handles[0])

try:
    driver = configure_webdriver()
    logging.info("Opened Chrome browser")
    driver.get("https://www.erome.com/search?q=%EF%BD%8Fnlyfans")
    logging.info("Opened search page")

    albums = WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.CLASS_NAME, "album-link")))

    cookies = driver.get_cookies()
    headers = {
        "User-Agent": driver.execute_script("return navigator.userAgent;"),
        "Referer": driver.current_url
    }
    headers.update(get_cookie_header(cookies))

    album_urls = [album.get_attribute('href') for album in albums]
    for album_url in album_urls:
        process_album(driver, album_url, headers)

except KeyboardInterrupt:
    logging.info("Quitting on keyboard interrupt...")
except NoSuchWindowException:
    logging.exception("Browser window closed unexpectedly")
except Exception:
    logging.exception("Unknown error occurred")
finally:
    driver.quit()
