import fitz  # PyMuPDF
import io
import os
from dataclasses import dataclass
from typing import List, Union, Optional
from PIL import Image
from pathlib import Path


@dataclass
class PageData:
    page_number: float
    text: str
    images: List[bytes]
    page_images: List[bytes]


class PDFExtractor:
    def __init__(
        self,
        scale: int = 2,
        multiplier: float = 1.0,
        min_dim: int = 200
    ):
        """
        Initialize the PDFExtractor with a given PDF data (bytes or BytesIO) and parameters.

        Args:
            pdf_data (Union[bytes, io.BytesIO]): PDF file data as bytes or BytesIO.
            scale (int): Scaling factor for rendering the PDF pages (default: 2).
            multiplier (float): Multiplier for determining page grouping or slicing (default: 1.0).
                               - If ≥ 1, determines how many pages to group together.
                               - If < 1, slices pages into parts, e.g., 0.5 means split in half.
            min_dim (int): Minimum dimension (width/height) for an image to be considered valid (default: 200).
        """
        self.scale = scale
        self.multiplier = multiplier
        self.min_dim = min_dim

    def _open_document(self, pdf_data: Union[bytes, io.BytesIO]) -> fitz.Document:
        """
        Open a PDF document from bytes or BytesIO.
        Returns:
            fitz.Document: The opened PDF document.
        """
        if isinstance(pdf_data, bytes):
            return fitz.open(stream=pdf_data, filetype="pdf")  # Open from bytes
        elif isinstance(pdf_data, io.BytesIO):
            return fitz.open(stream=pdf_data.getvalue(), filetype="pdf")  # Open from BytesIO
        else:
            raise ValueError("pdf_data must be either bytes or BytesIO.")

    def extract_pages(self, pdf_data: Union[bytes, io.BytesIO]) -> List[PageData]:
        """
        Extracts pages, grouped/sliced, from the PDF as PageData objects.

        Returns:
            List[PageData]: A list of extracted page data containing text, images, and rendered page images.
        """
        document = self._open_document(pdf_data=pdf_data)
        output = []

        page_index = 0
        while page_index < len(document):
            if self.multiplier >= 1:
                # Group pages together
                grouped_pages = self._extract_grouped_pages(document, page_index)
                if grouped_pages:
                    output.append(grouped_pages)
                if int(self.multiplier) > 1:
                    # Skip to the next group
                    page_index += int(self.multiplier) - 1
            else:
                # Split a page into slices
                output.extend(self._extract_sliced_page(document[page_index], page_index))

            page_index += 1

        document.close()
        return output

    def _extract_grouped_pages(
        self, document: fitz.Document, page_index: int
    ) -> Optional[PageData]:
        group_size = int(self.multiplier)
        if page_index % group_size != 0:
            return None

        grouped_pages = document[page_index : page_index + group_size]
        all_text = ""
        all_images = []
        page_images = []

        for page in grouped_pages:
            all_text += page.get_text("text") + "\n"
            pixmap = page.get_pixmap(matrix=fitz.Matrix(self.scale, self.scale))
            page_images.append(pixmap.tobytes("png"))

            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    image_data = document.extract_image(xref)["image"]
                    if self._is_valid_image(image_data):
                        all_images.append(image_data)
                except Exception:
                    continue

        return PageData(
            page_number=page_index,
            text=all_text.strip(),
            images=all_images,
            page_images=page_images,
        )

    def _extract_sliced_page(
        self, page: fitz.Page, page_index: int
    ) -> List[PageData]:
        splits = int(1 / self.multiplier)
        page_height = page.rect.height
        slice_height = page_height / splits
        pixmap = page.get_pixmap(matrix=fitz.Matrix(self.scale, self.scale))
        image_slices = self._render_partial_images(pixmap, splits)

        extracted_images = []
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                image_data = page.parent.extract_image(xref)["image"]
                if self._is_valid_image(image_data):
                    extracted_images.append(image_data)
            except Exception:
                continue

        blocks = page.get_text("dict")["blocks"]
        slice_texts = [""] * splits

        for block in blocks:
            bbox = block.get("bbox", [])
            y_center = (bbox[1] + bbox[3]) / 2
            slice_idx = min(int(y_center / slice_height), splits - 1)

            if block["type"] == 0:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        slice_texts[slice_idx] += span["text"] + " "

        return [
            PageData(
                page_number=page_index + i * self.multiplier,
                text=slice_texts[i].strip(),
                images=extracted_images if i == 0 else [],
                page_images=[image_slices[i]],
            )
            for i in range(splits)
        ]

    def _render_partial_images(self, pix: fitz.Pixmap, parts: int) -> List[bytes]:
        """
        Splits a pixmap into multiple parts horizontally and converts slices into bytes.

        Args:
            pix (fitz.Pixmap): The pixmap to split.
            parts (int): Number of horizontal slices.

        Returns:
            List[bytes]: List of byte-encoded PNG images of the slices.
        """
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        width, height = img.size
        slice_height = height // parts
        return [
            self._crop_to_bytes(
                img.crop((0, i * slice_height, width, (i + 1) * slice_height))
            )
            for i in range(parts)
        ]

    def _crop_to_bytes(self, pil_img: Image.Image) -> bytes:
        """
        Converts a cropped PIL image to bytes in PNG format.

        Args:
            pil_img (Image.Image): Cropped PIL Image object.

        Returns:
            bytes: Byte representation of the cropped image.
        """
        buffer = io.BytesIO()
        pil_img.save(buffer, format="PNG")
        return buffer.getvalue()

    def _is_valid_image(self, image_bytes: bytes) -> bool:
        """
        Validates if image dimensions meet the specified minimum threshold.

        Args:
            image_bytes (bytes): The image bytes to validate.

        Returns:
            bool: True if valid, False otherwise.
        """
        try:
            img = Image.open(io.BytesIO(image_bytes))
            return img.width >= self.min_dim and img.height >= self.min_dim
        except Exception:
            return False


class PageSaver:
    @staticmethod
    def save_page_data_to_disk(data_list: List[PageData], output_dir: str) -> None:
        """
        Saves a list of PageData objects to a specified directory on disk.

        Args:
            data_list (List[PageData]): List of PageData objects to save.
            output_dir (str): Path to the output directory.
        """
        os.makedirs(output_dir, exist_ok=True)

        for page_data in data_list:
            page_folder = Path(output_dir) / f"{page_data.page_number:.2f}"
            page_folder.mkdir(parents=True, exist_ok=True)

            # Save text
            text_path = page_folder / "text.txt"
            with open(text_path, "w", encoding="utf-8") as f:
                f.write(page_data.text)

            # Save page images
            for i, img_bytes in enumerate(page_data.page_images):
                img_path = page_folder / f"page_image_{i}.png"
                with open(img_path, "wb") as f:
                    f.write(img_bytes)

            # Save extracted images
            for i, img_bytes in enumerate(page_data.images):
                img_file = page_folder / f"img_{i}.png"
                with open(img_file, "wb") as f:
                    f.write(img_bytes)

        print(f"Saved {len(data_list)} page data entries to: {output_dir}")


if __name__ == "__main__":
    extractor = PDFExtractor(
        pdf_path="output.pdf",
        multiplier=3
    )
    pages = extractor.extract_pages()
    PageSaver.save_page_data_to_disk(pages, "output")