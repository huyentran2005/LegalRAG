import onnxruntime as ort
from transformers import AutoTokenizer
import numpy as np
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) 
onnx_path = os.path.join(BASE_DIR, "..", "models", "model_quint8_avx2.onnx")
onnx_path = os.path.normpath(onnx_path)
tokenizer_path = os.path.normpath(os.path.join(BASE_DIR, "..", "models"))


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)
session_options = ort.SessionOptions()
session_options.intra_op_num_threads = max(1, _env_int("EMBEDDING_INTRA_OP_THREADS", 1))
session_options.inter_op_num_threads = max(1, _env_int("EMBEDDING_INTER_OP_THREADS", 1))
session = ort.InferenceSession(
    onnx_path,
    sess_options=session_options,
    providers=["CPUExecutionProvider"],
)

def mean_pooling(token_embeddings, attention_mask):
    mask = np.expand_dims(attention_mask, -1).astype(np.float32)
    summed = np.sum(token_embeddings * mask, axis=1)
    counts = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)
    return summed / counts

def embed(texts):
    if not texts:
        return np.empty((0, 384), dtype=np.float32)
    inputs = tokenizer(texts, padding=True, truncation=True, max_length=512, return_tensors="np")
    ort_inputs = {
        "input_ids": inputs["input_ids"],
        "attention_mask": inputs["attention_mask"],
        "token_type_ids": inputs.get("token_type_ids", np.zeros_like(inputs["input_ids"])),
    }
    outputs = session.run(None, ort_inputs)
    token_embeddings = outputs[0]
    embeddings = mean_pooling(token_embeddings, inputs["attention_mask"])
    embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    return embeddings


def embed_batched(texts, batch_size: int | None = None):
    if batch_size is None:
        batch_size = _env_int("EMBEDDING_BATCH_SIZE", 8)
    batch_size = max(1, batch_size)

    batches = []
    for start in range(0, len(texts), batch_size):
        batches.append(embed(texts[start:start + batch_size]))

    if not batches:
        return np.empty((0, 384), dtype=np.float32)
    return np.vstack(batches)
