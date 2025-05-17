import requests
from typing import List
from io import BytesIO


class FileConvertor:
    SUPPORTED_EXTENSIONS: List[str] = [
        ".123",
        ".602",
        ".abw",
        ".bib",
        ".bmp",
        ".cdr",
        ".cgm",
        ".cmx",
        ".csv",
        ".cwk",
        ".dbf",
        ".dif",
        ".doc",
        ".docm",
        ".docx",
        ".dot",
        ".dotm",
        ".dotx",
        ".dxf",
        ".emf",
        ".eps",
        ".epub",
        ".fodg",
        ".fodp",
        ".fods",
        ".fodt",
        ".fopd",
        ".gif",
        ".htm",
        ".html",
        ".hwp",
        ".jpeg",
        ".jpg",
        ".key",
        ".ltx",
        ".lwp",
        ".mcw",
        ".met",
        ".mml",
        ".mw",
        ".numbers",
        ".odd",
        ".odg",
        ".odm",
        ".odp",
        ".ods",
        ".odt",
        ".otg",
        ".oth",
        ".otp",
        ".ots",
        ".ott",
        ".pages",
        ".pbm",
        ".pcd",
        ".pct",
        ".pcx",
        ".pdb",
        ".pdf",
        ".pgm",
        ".png",
        ".pot",
        ".potm",
        ".potx",
        ".ppm",
        ".pps",
        ".ppt",
        ".pptm",
        ".pptx",
        ".psd",
        ".psw",
        ".pub",
        ".pwp",
        ".pxl",
        ".ras",
        ".rtf",
        ".sda",
        ".sdc",
        ".sdd",
        ".sdp",
        ".sdw",
        ".sgl",
        ".slk",
        ".smf",
        ".stc",
        ".std",
        ".sti",
        ".stw",
        ".svg",
        ".svm",
        ".swf",
        ".sxc",
        ".sxd",
        ".sxg",
        ".sxi",
        ".sxm",
        ".sxw",
        ".tga",
        ".tif",
        ".tiff",
        ".txt",
        ".uof",
        ".uop",
        ".uos",
        ".uot",
        ".vdx",
        ".vor",
        ".vsd",
        ".vsdm",
        ".vsdx",
        ".wb2",
        ".wk1",
        ".wks",
        ".wmf",
        ".wpd",
        ".wpg",
        ".wps",
        ".xbm",
        ".xhtml",
        ".xls",
        ".xlsb",
        ".xlsm",
        ".xlsx",
        ".xlt",
        ".xltm",
        ".xltx",
        ".xlw",
        ".xml",
        ".xpm",
        ".zabw",
    ]

    def __init__(self, base_url: str) -> None:
        self.base_url: str = base_url

    def convert_to_pdf(self, input_data: BytesIO, file_extension: str) -> BytesIO:
        if file_extension.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file extension '{file_extension}'. Supported extensions: {', '.join(self.SUPPORTED_EXTENSIONS)}"
            )

        try:
            files = {"files": ("file" + file_extension, input_data)}
            endpoint = f"{self.base_url}/forms/libreoffice/convert"
            response = requests.post(endpoint, files=files)

            if response.status_code == 200:
                return BytesIO(response.content)
            else:
                response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Error during file conversion: {e}")


def main() -> None:
    base_url: str = "http://localhost:3000"
    converter: FileConvertor = FileConvertor(base_url)

    file_path: str = "/home/zain/Downloads/demo.docx"
    file_extension: str = ".docx"

    try:
        with open(file_path, "rb") as file:
            input_data = BytesIO(file.read())

        pdf_data = converter.convert_to_pdf(input_data, file_extension)

        with open("output.pdf", "wb") as pdf_file:
            pdf_file.write(pdf_data.getbuffer())

        print("Conversion successful. PDF saved as 'output.pdf'.")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
