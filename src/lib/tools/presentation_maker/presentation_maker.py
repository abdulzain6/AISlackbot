from .pptx.enum.shapes import MSO_SHAPE_TYPE
from .pptx import Presentation
from .exceptions import NoValidSequenceException
from .database import TemplateDBManager, TemplateModel, PlaceholderModel, SlideModel
from ..image_generator import ImageGenerator
from typing import Any, Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.pydantic_v1 import BaseModel, Field
from retrying import retry
from langchain.chat_models.base import BaseChatModel


import re
import os
import subprocess
import logging
import tempfile, time
import copy, six



class PresentationInput(BaseModel):
    topic: str
    instructions: str
    number_of_pages: int
    negative_prompt: str
    template_name: str


class PlaceholderData(BaseModel):
    placeholder_name: str = Field(
        description="The name of the placeholder. Make sure name is exactly same"
    )
    placeholder_data: str = Field(
        default="",
        description="The data to display in the placeholder. Make sure it fits in a presentaion slide.",
    )


class Placeholders(BaseModel):
    placeholders: List[PlaceholderData] = Field(description="The placeholder data")


class PresentationSequencePart(BaseModel):
    page_number: int = Field(
        description="The page number of the slide. Make sure this isn't repeated"
    )
    slide_detail: str = Field(
        description="What the slide should be about. This must be unique"
    )
    slide_type: str = Field(description="The type of the slide.")


class PresentationSequence(BaseModel):
    slide_sequence: List[PresentationSequencePart] = Field(
        description="The sequence of slides used to make the presentation"
    )


class CombinedPlaceholder(BaseModel):
    placeholder_name: str
    placeholder_data: str
    description: Optional[str] = None
    is_image: bool = False
    image_width: Optional[int] = None
    image_height: Optional[int] = None


class CombinedPlaceholders(BaseModel):
    placeholders: Optional[List[CombinedPlaceholder]] = Field(
        description="The combined placeholder data"
    )


class PresentationMaker:
    def __init__(
        self,
        template_manager: TemplateDBManager,
        llm: BaseChatModel,
        image_generator: ImageGenerator,
    ) -> None:
        self.template_manager = template_manager
        self.llm = llm
        self.image_generator = image_generator

    def format_placeholders(
        self, placeholders: List[PlaceholderModel], add_is_image: bool
    ) -> str:
        formatted_str = "Placeholders:\n"
        if not placeholders:
            formatted_str += "No placeholders."
        for placeholder in placeholders:
            formatted_str += f"  - Name: {placeholder.name}\n"
            formatted_str += f"    Description: {placeholder.description}\n"
            if add_is_image:
                formatted_str += f"    is image: {placeholder.is_image}\n"
        return formatted_str

    def format_slides(self, slides: List[SlideModel]) -> str:
        formatted_str = "Slides Information:\n"
        formatted_str += "=" * 40 + "\n"
        for slide in slides:
            formatted_str += f"Slide Type: {slide.slide_type}\n"
            formatted_str += self.format_placeholders(slide.placeholders, True)
            formatted_str += "=" * 40 + "\n"
        return formatted_str

    def make_slide_sequence_unique(
        self, slide_sequence: List[PresentationSequencePart]
    ) -> List[PresentationSequencePart]:
        seen = set()
        unique_sequence = []
        for slide in slide_sequence:
            if slide.slide_detail not in seen:
                unique_sequence.append(slide)
                seen.add(slide.slide_detail)
        return unique_sequence

    def create_sequence(
        self, template: TemplateModel, presentation_input: PresentationInput
    ) -> PresentationSequence:
        prompt = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(
                    """
You are an AI designed to assist in creating presentations. 
You are to pick a sequence of slides to create a presentation on the topic "{topic}".
THe presentation will be of {pages} pages (Important). 
Use a variety of slide types, keep in mind using a lot of slides with images can impact performance.
Dont pick same topic many times! Slide detail must be unique for every slide (Very Important)
The other AI helping fill the slides dont know if others exist so the slide detail must be unique!!
==========================================
You must follow the instructions above failure to do so will cause fatal error!
YOu must return the output in json
"""
                ),
                HumanMessagePromptTemplate.from_template(
                    """
Here are the available slides with the placeholders in them for automatic presentation generation:
==========================================
{slides}
==========================================

Must follow rules:
    1. Dont pick same topic many times! Slide detail must be unique for every slide (Very Important)
    2. The other AI helping fill the slides dont know if others exist so the slide detail must be unique!!
    {instructions}
===================
Lets think step by step, Looking at the slide types and the placeholders inside them 
Use a variety of slide types, keep in mind using a lot of slides with images can impact performance.
to create a sequence of slides that can be used to create a perfect presentation on {topic} of {pages} pages.
Do not choose slide types that are not shown to you.
Dont make slides with same heading and detail failure to do so will cause error. Last time you caused one!"""
                ),
            ],
            input_variables=[
                "topic",
                "pages",
                "instructions",
                "negative_prompt",
                "slides",
            ],
        )
        messages = prompt.format_messages(
            topic=presentation_input.topic,
            pages=presentation_input.number_of_pages,
            instructions=presentation_input.instructions,
            negative_prompt=presentation_input.negative_prompt,
            slides=self.format_slides(template.slides),
        )
        structured_llm = self.llm.with_structured_output(PresentationSequence)
        return structured_llm.invoke(messages)

    def validate_slides(
        self, template: TemplateModel, slides: PresentationSequence
    ) -> bool:
        slide_types = [slide.slide_type for slide in slides.slide_sequence]
        slides_to_choose_from = [slide.slide_type for slide in template.slides]
        return all(slide in slides_to_choose_from for slide in slide_types)

    @staticmethod
    def reduce_points_by_word_limit(
        text: str, word_limit: int, current_count: int
    ) -> Tuple[str, int]:
        points = text.split("\n")
        reduced_points = []
        current_word_count = current_count

        for point in points:
            point_word_count = len(point.split())
            new_word_count = current_word_count + point_word_count

            if new_word_count <= word_limit:
                reduced_points.append(
                    point.strip()
                )  # Remove leading/trailing whitespace
                current_word_count = new_word_count
            else:
                break

        return (
            "\n".join(reduced_points).strip(),
            current_word_count,
        )  # Remove leading/trailing whitespace

    @staticmethod
    def reduce_paragraph_by_word_limit(
        paragraph: str, word_limit: int, current_count: int
    ) -> Tuple[str, int]:
        sentences = paragraph.split(". ")
        reduced_paragraph = []
        current_word_count = current_count

        for sentence in sentences:
            sentence_word_count = len(sentence.split())
            new_word_count = current_word_count + sentence_word_count

            if new_word_count <= word_limit:
                reduced_paragraph.append(f"{sentence}.")
                current_word_count = new_word_count
            else:
                break

        return " ".join(reduced_paragraph).rstrip(), current_word_count

    @staticmethod
    def split_text_into_blocks(text: str) -> List[Tuple[str, str]]:
        blocks = []
        lines = text.split("\n")
        block = []
        block_type = None

        for i, line in enumerate(lines):
            stripped_line = line.strip()
            is_point = re.match(r"\d+\.", stripped_line) or stripped_line.startswith(
                ("-", "*")
            )
            is_empty = not stripped_line

            if block_type is None and not is_empty:
                block_type = "point" if is_point else "paragraph"

            if is_empty and block:
                blocks.append((block_type, "\n".join(block)))
                block = []
                block_type = None
                continue

            if block and is_point != (block_type == "point"):
                blocks.append((block_type, "\n".join(block)))
                block = [stripped_line]
                block_type = "point" if is_point else "paragraph"
                continue

            if not is_empty:
                block.append(stripped_line)

        if block:
            blocks.append((block_type, "\n".join(block)))

        return blocks

    @staticmethod
    def convert_numbered_list_to_bullet_points(text: str) -> str:
        return re.sub(r"\d+\.", "-", text)

    def auto_reduce_text_by_words(
        self,
        text: str,
        word_limit_points: int,
        word_limit_para: int,
        word_limit_hybrid: int,
    ) -> str:
        reduced_text = []
        current_word_count = 0
        blocks = self.split_text_into_blocks(text)

        is_hybrid = len({block_type for block_type, _ in blocks}) > 1

        for i, (block_type, block) in enumerate(blocks):
            if is_hybrid:
                word_limit = word_limit_hybrid
            else:
                word_limit = (
                    word_limit_points if block_type == "point" else word_limit_para
                )

            if block_type == "point":
                block = self.convert_numbered_list_to_bullet_points(block)
                reduced_block, current_word_count = self.reduce_points_by_word_limit(
                    block, word_limit, current_word_count
                )
            else:
                reduced_block, current_word_count = self.reduce_paragraph_by_word_limit(
                    block, word_limit, current_word_count
                )

            if reduced_block:
                reduced_text.append(reduced_block)

        return "\n".join(reduced_text).strip()  # Remove leading/trailing whitespace

    def combine_placeholders(
        self,
        slide_placeholders: List[PlaceholderModel],
        formatted_placeholders: List[PlaceholderData],
    ) -> CombinedPlaceholders:

        combined_list = []

        for slide_placeholder in slide_placeholders:
            for formatted_placeholder in formatted_placeholders:
                if slide_placeholder.name == formatted_placeholder.placeholder_name:
                    combined = CombinedPlaceholder(
                        placeholder_name=formatted_placeholder.placeholder_name,
                        placeholder_data=formatted_placeholder.placeholder_data,
                        description=slide_placeholder.description,
                        is_image=slide_placeholder.is_image,
                        image_width=slide_placeholder.image_width,
                        image_height=slide_placeholder.image_height,
                    )
                    combined_list.append(combined)

        return CombinedPlaceholders(placeholders=combined_list)

    def get_slide_content(
        self,
        sequence_part: PresentationSequencePart,
        slide: SlideModel,
        presentation_input: PresentationInput,
        all_slides: list[PresentationSequencePart],
        word_limit_para: int,
        word_limit_points: int,
        word_limit_hybrid: int,
    ) -> Placeholders:
        prompt = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(
                    """
You are an AI designed to assist in automatic presentation generation.
You will generate content for a slide by looking at placeholders and return what should they be filled with.
Ordered or unordered list points must be short(Very importsnt)
Make sure content fills the slide.

Follow the following instructions:
==============
You must fill all placeholders.
If there are no placeholders return an empty list.
{instructions}
==============

Do not do the following:
==============
Do not choose slide types that are not shown to you.
{negative_prompt}
==============
Never leave a placeholder empty!
You must follow the instructions above failure to do so will cause fatal error!
YOu must return the output in json
"""
                ),
                HumanMessagePromptTemplate.from_template(
                    """
=====================
The presentation is about {presentation_topic}
Here are all the slides for the presentation:
{slides}
=====================


The slide you will generate content for is {slide_detail}. This is page {page_no} of the ppt
Dont duplicate content!

Here are the placeholders we want to fill:
=====================
{placeholders}
=====================

{help_text}

Ordered or unordered list points must be short and should start with "-" (Very important)
For example:
    - Cat
    - Dog
End of example

You must follow the instructions above failure to do so will cause fatal error!
Lets think step by step, Looking at the placeholders and their descriptions to fill them for the slide topic {slide_detail}. Follow all rules above! Ensure it fits in a slide
Follow the damn rules, you gave 150 words for a placeholder last time that caused error so keep it within slide limits.
Titles and subtitles must be even shorter only content placeholders can have more words. Please adhere to this (IMportant)
"""
                ),
            ],
            input_variables=[
                "placeholders",
                "slide_detail",
                "slides",
                "presentation_topic",
                "instructions",
                "negative_prompt",
                "page_no",
                "help_text",
            ],
        )

        help_text = "Use your own knowledge to fill the placeholders"
        structured_llm = self.llm.with_structured_output(Placeholders)
        messages = prompt.format_messages(
            placeholders=self.format_placeholders(slide.placeholders, True),
            slide_detail=sequence_part.slide_detail,
            slides="\n".join([slide.slide_detail for slide in all_slides]),
            presentation_topic=presentation_input.topic,
            instructions=presentation_input.instructions,
            negative_prompt=presentation_input.negative_prompt,
            page_no=sequence_part.page_number,
            help_text=help_text,
        )
        placeholders: Placeholders = structured_llm.invoke(messages)
        for placeholder in placeholders.placeholders:
            placeholder.placeholder_data = placeholder.placeholder_data.replace(
                "\n\n", "\n"
            )
            try:
                placeholder.placeholder_data = str(
                    self.auto_reduce_text_by_words(
                        placeholder.placeholder_data,
                        word_limit_para=word_limit_para,
                        word_limit_points=word_limit_points,
                        word_limit_hybrid=word_limit_hybrid,
                    )
                )
            except Exception as e:
                logging.error(f"Error in presentation (get_slide_content) {e}")

        return self.combine_placeholders(slide.placeholders, placeholders.placeholders)

    def remove_placeholders_and_artifacts(self, slide) -> None:
        """
        Removes empty placeholders and other artifacts from a slide.

        Args:
        slide (Slide): The slide to clean up.

        Returns:
        None
        """
        shapes_to_remove = []

        for shape in slide.shapes:
            try:
                if shape.shape_type == MSO_SHAPE_TYPE.PLACEHOLDER and (
                    shape.has_text_frame and not shape.text
                ):
                    shapes_to_remove.append(shape)
            except Exception as e:
                logging.error(
                    f"An error occurred while processing the shape (remove_placeholders_and_artifacts): {e}"
                )

        for shape in shapes_to_remove:
            sp = shape._element
            sp.getparent().remove(sp)

    def duplicate_slide_with_temp_img(
        self, prs: Presentation, slide_index: int, layout_index: int
    ) -> None:
        template = prs.slides[slide_index]

        # Try to get the layout as specified, else use the last available layout
        try:
            blank_slide_layout = prs.slide_layouts[layout_index]
        except IndexError:
            blank_slide_layout = prs.slide_layouts[-1]

        copied_slide = prs.slides.add_slide(blank_slide_layout)

        # Copy shapes
        for shp in template.shapes:
            el = shp.element
            new_el = copy.deepcopy(el)
            copied_slide.shapes._spTree.insert_element_before(new_el, "p:extLst")

        # Copy relationships (excluding notes)
        for _, value in six.iteritems(template.part.rels):
            if "notesSlide" not in value.reltype:
                copied_slide.part.rels.add_relationship(
                    value.reltype, value._target, value.rId
                )

        # Remove placeholders if needed
        self.remove_placeholders_and_artifacts(copied_slide)

    def create_presentation_from_sequence(
        self,
        sequence: PresentationSequence,
        template_path: str,
        template_slides: List[SlideModel],
    ) -> Presentation:

        # Create the slide_type to layout_index mapping dynamically
        slide_type_to_layout_index = {
            slide.slide_type: slide.page_number - 1 for slide in template_slides
        }

        # Step 1: Load Template Presentation
        prs = Presentation(template_path)

        # Step 2: Iterate Through the Sequence
        for slide_part in sequence.slide_sequence:

            if slide_model := next(
                (
                    slide
                    for slide in template_slides
                    if slide.slide_type == slide_part.slide_type
                ),
                None,
            ):
                index_to_duplicate = slide_model.page_number - 1

                # Use the mapping to get the layout index
                layout_index = slide_type_to_layout_index.get(slide_part.slide_type, 0)

                # Debugging: Slide Count Before Duplication

                self.duplicate_slide_with_temp_img(
                    prs, index_to_duplicate, layout_index
                )

                # Debugging: Slide Count After Duplication

        # Step 3: Delete All Original Slides
        for i in range(len(prs.slides) - len(sequence.slide_sequence) - 1, -1, -1):
            rId = prs.slides._sldIdLst[i].rId
            prs.part.drop_rel(rId)
            del prs.slides._sldIdLst[i]

        return prs

    def fill_single_slide(
        self,
        i: int,
        slide_part: Any,
        prs: Presentation,
        template_slides: List[Any],
        presentation_input: Any,
        sequence: Any,
        word_limit_para: int,
        word_limit_points: int,
        word_limit_hybrid: int,
    ) -> tuple[Placeholders, int]:
        slide_content_obtained = (
            False  # Flag to check if slide content was successfully obtained
        )

        try:
            template_slide = self.get_slide_by_type(
                slide_part.slide_type, template_slides
            )

            for _ in range(3):
                try:
                    slide_content = self.get_slide_content(
                        slide_part,
                        template_slide,
                        presentation_input,
                        sequence.slide_sequence,
                        word_limit_para,
                        word_limit_points,
                        word_limit_hybrid,
                    )
                    slide_content_obtained = (
                        True  # Set the flag to True if content is obtained
                    )
                    break
                except Exception as e:
                    logging.error(f"Error in presentation (fill_single_slide){e}")

            if not slide_content_obtained:
                logging.error(
                    f"Failed to get content for slide {i + 1}. Deleting the slide."
                )
                rId = prs.slides._sldIdLst[i].rId
                prs.part.drop_rel(rId)
                del prs.slides._sldIdLst[i]
                return

            presentation_slide = prs.slides[i]
            self.replace_placeholders_in_single_slide(presentation_slide, slide_content)
            return slide_content, i
        except Exception as e:
            logging.error(f"Error in presentation (fill_single_slide){e}")

    def fill_presentation_with_content(
        self,
        prs: Presentation,
        sequence: PresentationSequence,
        presentation_input: PresentationInput,
        template: TemplateModel,
    ) -> List[CombinedPlaceholders]:
        results = []

        def wrapper_fill_single_slide(index: int, *args) -> Placeholders:
            return self.fill_single_slide(*args)  # Return the result

        with ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(
                    wrapper_fill_single_slide,
                    i,
                    i,
                    slide_part,
                    prs,
                    template.slides,
                    presentation_input,
                    sequence,
                    template.word_limit_para,
                    template.word_limit_points,
                    template.word_limit_hybrid,
                )
                for i, slide_part in enumerate(sequence.slide_sequence)
            ]

            for future in as_completed(futures):
                results.append(future.result())  # Collect the results as they complete

        sorted_results = sorted(results, key=lambda x: x[1])
        return [content for content, _ in sorted_results]

    @retry(stop_max_attempt_number=3)
    def make_presentation(
        self, presentation_input: PresentationInput
    ) -> tuple[str, list[dict]]:
        logging.info("Fetching best template...")
        start_time = time.time()
        template_name = presentation_input.template_name
        slide_path = self.template_manager.get_template_file(template_name)
        template = self.template_manager.read_template(template_name)

        if not slide_path:
            raise ValueError("Template Not found!")

        for _ in range(3):
            logging.info("Creating and validating slide sequence...")
            try:
                sequence = PresentationSequence(
                    slide_sequence=self.make_slide_sequence_unique(
                        self.create_sequence(
                            template, presentation_input
                        ).slide_sequence
                    )
                )
                if self.validate_slides(template, sequence):
                    break
            except Exception as e:
                logging.error(f"Error (make_presentation){e}")

        else:
            raise NoValidSequenceException("Couldn't find the best sequence")

        sequence.slide_sequence = sorted(
            sequence.slide_sequence, key=lambda x: x.page_number if x else 0
        )

        prs = self.create_presentation_from_sequence(
            sequence, slide_path, template.slides
        )

        content = self.fill_presentation_with_content(
            prs, sequence, presentation_input, template
        )
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as temp_file:
            prs.save(temp_file.name)
            temp_pptx_path = temp_file.name  # Store the path for returning

        logging.info(f"Original name: {temp_pptx_path}")

        # Step 2: Define output path and run the conversion
        temp_ppt_path = temp_pptx_path.replace(".pptx", ".ppt")

        # Ensure no existing .ppt file at this path (clean up)
        if os.path.exists(temp_ppt_path):
            os.remove(temp_ppt_path)

        # Convert to .ppt using LibreOffice
        subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--convert-to",
                "ppt",
                "--outdir",
                tempfile.gettempdir(),
                temp_pptx_path,
            ],
            check=True,
        )

        if os.path.exists(temp_pptx_path):
            os.remove(temp_pptx_path)

        if not os.path.exists(temp_ppt_path):
            raise FileNotFoundError(
                f"Conversion failed, .ppt file not found at {temp_ppt_path}"
            )

        subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--convert-to",
                "pptx",
                "--outdir",
                tempfile.gettempdir(),
                temp_ppt_path,
            ],
            check=True,
        )

        # Step 3: Confirm conversion and return path

        logging.info(
            f"Presentation saved and converted successfully. Time taken: {time.time() - start_time}"
        )

        return temp_pptx_path, [
            {**placeholders.dict(), **sequence.dict()}
            for placeholders, sequence in zip(content, sequence.slide_sequence)
        ]

    def replace_text_in_run(self, run, placeholders: List[CombinedPlaceholder]) -> None:
        for placeholder in placeholders:
            if not placeholder.is_image and placeholder.placeholder_name in run.text:
                # Perform the replacement
                run.text = run.text.replace(
                    "{{" + placeholder.placeholder_name + "}}",
                    placeholder.placeholder_data,
                ).replace("*", "")

    def replace_images_in_shape(
        self, shape, placeholders: List[CombinedPlaceholder]
    ) -> List[Tuple[str, int, int, int, int]]:
        new_shapes = []

        for placeholder in placeholders:
            if placeholder.is_image:
                image_bytes = self.image_generator.generate_image(
                    prompt=placeholder.placeholder_data,
                    negative_prompt="",
                    width=placeholder.image_width,
                    height=placeholder.image_height,
                ).read()

                # Create a temporary file
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".png"
                ) as temp_file:
                    temp_file.write(image_bytes)
                    temp_file_path = temp_file.name

                left = shape.left
                top = shape.top
                width = shape.width
                height = shape.height

                new_shapes.append((temp_file_path, left, top, width, height))
        return new_shapes

    def process_text_frame(
        self, text_frame, placeholders: List[CombinedPlaceholder]
    ) -> None:
        for paragraph in text_frame.paragraphs:
            for run in paragraph.runs:
                self.replace_text_in_run(run, placeholders)

    def process_table(self, table, placeholders: List[CombinedPlaceholder]) -> None:
        for row in table.rows:
            for cell in row.cells:
                if cell.text_frame:
                    self.process_text_frame(cell.text_frame, placeholders)

    def replace_placeholders_in_single_slide(
        self, slide, placeholders: CombinedPlaceholders
    ) -> None:
        shapes_to_remove = []
        shapes_to_add = []

        def process_shape(shape):
            try:
                nonlocal shapes_to_remove, shapes_to_add

                if shape.has_text_frame:
                    self.process_text_frame(shape.text_frame, placeholders.placeholders)
                elif shape.has_table:
                    self.process_table(shape.table, placeholders.placeholders)

                if shape.shape_type == 13:
                    image_placeholders = [
                        placeholder
                        for placeholder in placeholders.placeholders
                        if placeholder.is_image
                        and shape.name == placeholder.placeholder_name
                    ]

                    def download_image(placeholder):
                        nonlocal shapes_to_add
                        images = self.replace_images_in_shape(shape, [placeholder])
                        shapes_to_add.extend(images)

                    with ThreadPoolExecutor() as executor:
                        executor.map(download_image, image_placeholders)

                    shapes_to_remove.append(shape)
            except Exception as e:
                logging.error(f"Error in presentation (process_shape) {e}")

        with ThreadPoolExecutor(max_workers=len(slide.shapes)) as executor:
            executor.map(process_shape, slide.shapes)

        for shape in shapes_to_remove:
            slide.shapes._spTree.remove(shape._element)

        for temp_file_name, left, top, width, height in shapes_to_add:
            try:
                new_shape = slide.shapes.add_picture(
                    temp_file_name, left, top, width, height
                )
            except Exception as e:
                logging.error(f"An error occurred while adding the picture: {e}")

    def get_slide_by_type(self, type: str, slides: list[SlideModel]) -> SlideModel:
        for slide in slides:
            if slide.slide_type.lower() == type.lower():
                return slide


