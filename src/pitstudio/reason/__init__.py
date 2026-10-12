"""Vision-language reasoning lane (spec 015, M22): exact scene truth, task builders and scoring (NumPy only, no GPU).

The GPU side (llama.cpp driver, GGUF conversion, the BF16 reference) lives in `pitstudio_pipeline.reason`; this package
holds what CI can test: the frame-state loader, the task-A ground truth and query builder, the answer parser, the
detector rule, the scoring statistics, the task-B pair builder, the caption scorer and the publication guards.
"""
