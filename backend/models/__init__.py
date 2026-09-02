# backend.models — specialist model wrappers (vqa, grounding, change, fusion)
# Each specialist exposes: predict(images, query, task) -> {answer, evidence, confidence}
# plus helpers: is_real(), load_error(), get_model_info(), preload()

from . import vqa as vqa_specialist  # real adapter-backed
from . import grounding as grounding_specialist  # stub
from . import change as change_specialist  # stub
from . import fusion as fusion_specialist  # stub

__all__ = ["vqa_specialist", "grounding_specialist", "change_specialist", "fusion_specialist"]
