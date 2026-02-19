import os
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
import shutil
import streamlit as st
from io import BytesIO

st.set_page_config(page_title="Scribd PDF Downloader", layout="centered")
st.title("🌐 Scribd PDF Downloader")


def generate_pdf(link):
    mis = 0

    contentcode = link.split("/")[-2]
    url = f"https://www.scribd.com/embeds/{contentcode}/content"

    output_folder = f"downloaded_images_{contentcode}"
    os.makedirs(output_folder, exist_ok=True)

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    data = response.text

    # -------- Direct image extraction --------
    direct_images = re.findall(
        r'(https://[^\s"\'<>]+?\.(?:jpg|png))',
        data,
        re.IGNORECASE
    )

    direct_images = list(dict.fromkeys(direct_images))

    image_index = 1

    for img_url in direct_images:
        try:
            resp = requests.get(img_url, timeout=30)
            resp.raise_for_status()

            img_path = os.path.join(output_folder, f"image_{image_index}.jpg")

            with open(img_path, "wb") as f:
                f.write(resp.content)

            image_index += 1

        except:
            image_index += 1
            mis += 1

    # -------- Extract contentUrls --------
    content_urls = re.findall(r'contentUrl:\s*"([^"]+)"', data)

    def process_content_url(idx_url_pair):
        idx, url = idx_url_pair
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()

            jsonp_text = resp.text

            jsonp_match = re.search(
                r'\(\s*\[\s*"(.+)"\s*\]\s*\);',
                jsonp_text,
                re.DOTALL
            )

            if not jsonp_match:
                return

            raw_html_escaped = jsonp_match.group(1)
            html_content = bytes(
                raw_html_escaped,
                "utf-8"
            ).decode("unicode_escape")

            orig_match = re.search(
                r'orig="([^"]*\.[^"]*)"',
                html_content
            )

            if orig_match:
                image_url = orig_match.group(1)

                image_resp = requests.get(image_url, timeout=30)
                image_resp.raise_for_status()

                image_filename = os.path.join(
                    output_folder,
                    f"image_{image_index + idx}.jpg"
                )

                with open(image_filename, "wb") as img_file:
                    img_file.write(image_resp.content)

        except:
            pass

    if content_urls:
        max_threads = min(8, len(content_urls))
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = [
                executor.submit(process_content_url, (i + 1, url))
                for i, url in enumerate(content_urls)
            ]
            for _ in as_completed(futures):
                pass

    # -------- Create PDF --------
    image_extensions = (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp")

    image_files = [
        os.path.join(output_folder, f)
        for f in os.listdir(output_folder)
        if f.lower().endswith(image_extensions)
    ]

    image_files.sort(
        key=lambda x: int(re.search(r'(\d+)', os.path.basename(x)).group(1))
        if re.search(r'(\d+)', os.path.basename(x))
        else -1
    )

    if not image_files:
        shutil.rmtree(output_folder)
        raise Exception("No images found.")

    image_list = []
    for img_path in image_files:
        img = Image.open(img_path).convert("RGB")
        image_list.append(img)

    pdf_buffer = BytesIO()

    first_image = image_list.pop(0)
    first_image.save(
        pdf_buffer,
        format="PDF",
        save_all=True,
        append_images=image_list
    )

    pdf_buffer.seek(0)

    shutil.rmtree(output_folder)

    return pdf_buffer, mis, contentcode


# ------------------ STREAMLIT UI ------------------

link = st.text_input("Enter Scribd embed link")

if st.button("Generate PDF"):

    if not link:
        st.warning("Please enter a valid link.")
        st.stop()

    try:
        with st.spinner("Downloading pages and creating PDF... ⏳"):
            pdf_buffer, mis, contentcode = generate_pdf(link)

        st.success("PDF Generated Successfully!")
        st.write("Pages Failed:", mis)

        st.download_button(
            "📥 Download PDF",
            data=pdf_buffer,
            file_name=f"{contentcode}.pdf",
            mime="application/pdf"
        )

    except Exception as e:
        st.error(f"Error: {e}")
