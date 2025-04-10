import json
import os
from pydantic import BaseModel
from typing import Optional, List, Union
from typing import List, Union, Optional


DEFAULT_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "template_dir")
DEFAULT_TEMPLATES_JSON = os.path.join(os.path.dirname(os.path.realpath(__file__)), "templates.json")



class PlaceholderModel(BaseModel):
    name: str
    description: Optional[str] = None
    is_image: bool = False
    image_width: Optional[int] = None
    image_height: Optional[int] = None


class SlideModel(BaseModel):
    slide_type: str
    page_number: int
    placeholders: List[PlaceholderModel]


class TemplateModel(BaseModel):
    template_name: str
    template_description: str
    category: Optional[str] = None
    version: Optional[str] = None
    aspect_ratio: Optional[str] = None
    color_scheme: Optional[List[str]] = None
    slides: List[SlideModel]
    file_extension: str = "pptx"
    word_limit_para: int = 93
    word_limit_points: int = 80
    word_limit_hybrid: int = 75
    file_name: Optional[str] = None 
    image_base64: Optional[str] = None


class TemplateDBManager:
    def __init__(
        self,
        templates_json_path: str,
        template_dir: str,
    ) -> None:
        self.template_dir = template_dir
        self.templates_json_path = templates_json_path
        self.templates = self.load_templates(templates_json_path)
        
    def add_template_to_json(self, template_json_file: str, template: TemplateModel):
        with open(template_json_file, "r+") as fp:
            self.templates.append(template)
            json.dump(self.templates, fp)
        
    def load_templates(self, template_json_file: str = "templates.json") -> List[TemplateModel]:
        with open(template_json_file, "rt") as fp:
            templates = json.load(fp)

        return [TemplateModel.model_validate(template) for template in templates]

    def find_template_by_name(self, template_name: str) -> Optional[TemplateModel]:
        for template in self.templates:
            if template.template_name == template_name:
                return template

    def read_template(self, template_name: str) -> Union[TemplateModel, None]:
        temp = self.find_template_by_name(template_name)
        return temp if temp else None

    def get_all_templates(self) -> List[TemplateModel]:
        return self.templates

    def get_template_file(self, template_name: str) -> Union[str, None]:
        doc = self.find_template_by_name(template_name)
        return os.path.join(self.template_dir, doc.file_name)