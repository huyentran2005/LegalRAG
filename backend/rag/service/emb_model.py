import onnxruntime as ort
from transformers import AutoTokenizer
import numpy as np
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) 
onnx_path = os.path.join(BASE_DIR, "..", "models", "model_quint8_avx2.onnx")
onnx_path = os.path.normpath(onnx_path)
tokenizer_path = os.path.normpath(os.path.join(BASE_DIR, "..", "models"))


tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)
session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])

def mean_pooling(token_embeddings, attention_mask):
    mask = np.expand_dims(attention_mask, -1).astype(np.float32)
    summed = np.sum(token_embeddings * mask, axis=1)
    counts = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)
    return summed / counts

def embed(texts):
    inputs = tokenizer(texts, padding=True, truncation=True, return_tensors="np")
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

