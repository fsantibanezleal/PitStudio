"""The reason lane (spec 015, M22) in the pipeline environment: pinned llama.cpp runtime, model provenance, own GGUF
conversion, the loopback `llama-server` driver, the transformers BF16 reference and the `st59_*` stages.

Everything that needs a GPU, a hub or a child process is reached through a seam that the tests replace with a fake
(a hub object, a command runner, a launcher); the scoring and the task builders live in the root package
`pitstudio.reason`.
"""
