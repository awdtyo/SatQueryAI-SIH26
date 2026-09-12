# backend.models — specialist model wrappers (vqa, grounding, change, fusion)
# Each specialist exposes: predict(images, query, task) -> {answer, evidence, confidence}
# plus helpers: is_real(), load_error(), get_model_info(), preload()

from . import vqa as vqa_specialist  # real adapter-backed (Qwen2-VL-2B)
from . import grounding as grounding_specialist  # real via vqa adapter (Stage 2 VRSBench)
from . import change as change_specialist  # real — CDVQA bi-temporal (imadityasarkar/cdvqa_change)
from . import fusion as fusion_specialist  # real — optical-SAR fusion via Phase-2 VRSBench (imadityasarkar/satquery-phase2-vrsbench)

__all__ = ["vqa_specialist", "grounding_specialist", "change_specialist", "fusion_specialist"]
