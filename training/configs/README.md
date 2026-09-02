# Training Configs

Per-dataset configs (bigearthnet, vrsbench, rsvqa, cdvqa).

- `bigearthnet_stage1.json` — Stage 1: BigEarthNet vision-language adaptation (Qwen2-VL-2B, QLoRA r=16, batch 1×8, save_steps=25). Used by `satquery_ai_qlora_finetune.ipynb`.
- Copy and adapt for `vrsbench_rsvqa_sft.json` (stage 2) and `cdvqa_change_sft.json` (stage 3): change `subset_size`, `adapter_to_continue` (point to previous stage adapter on Drive), and `learning_rate` (typically 1e-4 for SFT stages).
- All configs are also mirrored to Drive (`/content/drive/MyDrive/SatQueryAI/training_config_stage1.json`) when the notebook runs.
