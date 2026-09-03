# Training Configs

Per-dataset configs (bigearthnet, vrsbench, rsvqa, cdvqa).

- `bigearthnet_stage1.json` — Stage 1: BigEarthNet vision-language adaptation (Qwen2-VL-2B, QLoRA r=16, batch 1×8, save_steps=25). Used by `satquery_ai_qlora_finetune.ipynb`.
- `vrsbench_rsvqa_stage2.json` — Stage 2: VRSBench/RSVQA SFT continuing from stage1 adapter (`adapter_to_continue=imadityasarkar/satquery-qwen2vl-stage1-bigearthnet`, lr 1e-4, subset 1200). Used by `vrsbench_rsvqa_sft.ipynb` (`CHECKPOINT_DIR=stage2_vrsbench_sft`, `DATASET_CACHE_DIR=vrsbench_subset`).
- `cdvqa_stage3.json` — Stage 3: CDVQA bi-temporal change SFT continuing from stage2 (`adapter_to_continue=imadityasarkar/satquery-qwen2vl-stage2-vrsbench`, lr 1e-4, subset 1000, paired-image loader). Used by `cdvqa_change_sft.ipynb` (`CHECKPOINT_DIR=stage3_cdvqa_change`, `DATASET_CACHE_DIR=cdvqa_subset`).
- All configs are also mirrored to Drive (`/content/drive/MyDrive/SatQueryAI/training_config_stage{1,2,3}_*.json`) when the respective notebook runs.
