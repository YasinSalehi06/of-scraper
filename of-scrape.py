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
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(format="[%(levelname)s] of-scraper: %(message)s", level=logging.INFO)
logging.info("Starting...")

def sanitize_filename(filename):
    """Sanitize filename by removing illegal characters, converting to lowercase, and replacing spaces with underscores."""
    sanitized = re.sub(r'[<>:"/\\|?*\n\r\t]', '', filename)
    sanitized = sanitized.replace(' ', '_')
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

def process_album(driver, album_url):
    """Process an album by extracting image and video URLs."""
    driver.execute_script(f"window.open('{album_url}', '_blank');")
    driver.switch_to.window(driver.window_handles[-1])
    try:
        title = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//h1"))).text
        sanitized_title = sanitize_filename(title)
        img_elements = WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.XPATH, "//div[@class='img']")))
        video_elements = WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.XPATH, "//source[@type='video/mp4']")))

        img_urls = [img.get_attribute('data-src') for img in img_elements]
        video_urls = [video.get_attribute('src') for video in video_elements]

        return sanitized_title, img_urls, video_urls
    except TimeoutException:
        logging.warning(f"Timeout while processing album: {album_url}")
        return None, [], []
    except Exception as e:
        logging.error(f"Error while processing album {album_url}: {e}")
        return None, [], []
    finally:
        driver.close()
        driver.switch_to.window(driver.window_handles[0])

def download_files_concurrently(urls, directory, headers=None, max_workers=5):
    """Download files from a list of URLs concurrently using ThreadPoolExecutor."""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for url in urls:
            if url:
                futures.append(executor.submit(download_file, url, directory, headers))

        for future in as_completed(futures):
            try:
                future.result()  # This will raise an exception if the download failed
            except Exception as e:
                logging.error(f"An error occurred during download: {e}")

try:
    driver = configure_webdriver()
    logging.info("Opened Chrome browser")
    driver.get("https://www.erome.com/DFinfinite")
    logging.info("Opened search page")

    albums = WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.CLASS_NAME, "album-link")))

    cookies = driver.get_cookies()
    headers = {
        "User-Agent": driver.execute_script("return navigator.userAgent;"),
        "Referer": driver.current_url
    }
    headers.update(get_cookie_header(cookies))

    album_urls = [album.get_attribute('href') for album in albums]

    all_downloads = []
    seen_urls = set()  # Initialize set to keep track of processed URLs

    for album_url in album_urls:
        title, img_urls, video_urls = process_album(driver, album_url)
        if title:
            sanitized_title = sanitize_filename(title)
            for url in img_urls + video_urls:
                if url and url not in seen_urls:  # Check if URL has already been processed and ensure it's not None
                    seen_urls.add(url)  # Add URL to the set
                    all_downloads.append((url, sanitized_title))

    # Download all files concurrently
    for url, directory in all_downloads:
        os.makedirs(directory, exist_ok=True)
        urls = [url for url, _ in all_downloads if _ == directory]
        download_files_concurrently(urls, directory, headers)

except KeyboardInterrupt:
    logging.info("Quitting on keyboard interrupt...")
except NoSuchWindowException:
    logging.exception("Browser window closed unexpectedly")
except Exception as e:
    logging.exception(f"Unknown error occurred: {e}")
finally:
    driver.quit()
