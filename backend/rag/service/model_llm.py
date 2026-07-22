import importlib.util
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from transformers import pipeline
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
MODEL_DIR = BASE_DIR / "models" / "Qwen2.5-0.5B-Instruct"


class ChatTemplateLLM:
    """
    Wrapper thay thế HuggingFacePipeline trực tiếp: áp dụng chat template
    (tokenizer.apply_chat_template) trước khi generate, để model Instruct
    hiểu đúng đây là 1 instruction thay vì raw text cần "tiếp tục viết".
    """

    def __init__(self, hf_pipeline, tokenizer, system_prompt: str | None = None):
        self.pipeline = hf_pipeline
        self.tokenizer = tokenizer
        self.system_prompt = system_prompt or (
            "Bạn là trợ lý AI phân tích tài liệu tiếng Việt, trả lời chính xác, "
            "chỉ dựa trên tài liệu được cung cấp, không được bịa thông tin."
        )

    def invoke(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ]
        formatted = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        out = self.pipeline(formatted)
        if isinstance(out, list) and out:
            first = out[0]
            if isinstance(first, dict) and "generated_text" in first:
                return first["generated_text"]
            return str(first)
        return str(out)

    def __call__(self, prompt: str) -> str:
        return self.invoke(prompt)


def get_hf_llm(
    model_name: str = str(MODEL_DIR),
    device: str = "auto",
    temperature: float = 0.2,
    max_new_tokens: int = 450,
    **kwargs
):
    has_accelerate = importlib.util.find_spec("accelerate") is not None
    requested_device = device.lower()
    if requested_device not in {"auto", "cuda", "cpu"}:
        raise ValueError("LLM device must be one of: auto, cuda, cpu")

    cuda_available = torch.cuda.is_available()
    if requested_device == "cuda" and not cuda_available:
        raise RuntimeError("LLM_DEVICE=cuda was requested, but CUDA is not available.")

    use_cuda = requested_device == "cuda" or (requested_device == "auto" and cuda_available)
    model_dtype = torch.float16 if use_cuda else torch.float32

    model_kwargs = {
        "dtype": model_dtype,
        "low_cpu_mem_usage": True,
    }
    if has_accelerate and use_cuda:
        model_kwargs["device_map"] = "auto"

    model = AutoModelForCausalLM.from_pretrained(model_name, **model_kwargs)
    if use_cuda and not has_accelerate:
        model = model.to("cuda")  # type: ignore

    tokenizer = AutoTokenizer.from_pretrained(model_name)

    model_pipeline = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        temperature=temperature,
        max_new_tokens=max_new_tokens,
        pad_token_id=tokenizer.eos_token_id,
        do_sample=True,
        top_p=0.75,
        repetition_penalty=1.15,   # giảm từ 1.3 -> nhẹ tay hơn, tránh đẩy model vào token lạ/hỏng mạch văn
        no_repeat_ngram_size=4,    # nới từ 3 -> 4, vẫn chống lặp câu dài nhưng ít ép buộc hơn
        return_full_text=False,
    )

    # Thay vì HuggingFacePipeline (gửi raw string), dùng wrapper áp dụng
    # chat template đúng chuẩn Qwen2.5-Instruct.
    return ChatTemplateLLM(model_pipeline, tokenizer)