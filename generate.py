"""Single-shot text generation with local thinking-capable models."""

import argparse

from thoughtbench.config import DEFAULT_MODEL_ID, MODEL_CATALOG, get_model_option
from thoughtbench.model import split_model_response
from thoughtbench.model_loading import load_processor_and_model, model_input_device


def main():
    model_ids = tuple(option.model_id for option in MODEL_CATALOG)
    parser = argparse.ArgumentParser(description="Generate text with a curated local model")
    parser.add_argument("prompt", help="The prompt to send to the model")
    parser.add_argument(
        "--model-id",
        choices=model_ids,
        default=DEFAULT_MODEL_ID,
        help="Curated model ID to load.",
    )
    parser.add_argument(
        "--think", action="store_true", help="Enable thinking / reasoning mode"
    )
    parser.add_argument(
        "--max-tokens", type=int, default=2048, help="Max new tokens to generate"
    )
    parser.add_argument(
        "--system", default="You are a helpful assistant.", help="System prompt"
    )
    parser.add_argument(
        "--load-mode",
        choices=("auto", "bf16", "4bit"),
        default=None,
        help="Model loading mode. auto uses 4-bit on GPUs below 12 GB VRAM.",
    )
    args = parser.parse_args()

    option = get_model_option(args.model_id)
    print(f"Loading {option.display_name} ({option.model_id}) ...")
    processor, model, load_info = load_processor_and_model(
        option.model_id,
        args.load_mode,
        option,
    )
    print(f"Model loaded ({load_info.detail}).")

    messages = [
        {"role": "system", "content": args.system},
        {"role": "user", "content": args.prompt},
    ]

    text = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=args.think and option.supports_thinking,
    )
    inputs = processor(text=text, return_tensors="pt").to(model_input_device(model))
    input_len = inputs["input_ids"].shape[-1]

    outputs = model.generate(
        **inputs,
        max_new_tokens=args.max_tokens,
        temperature=1.0,
        top_p=0.95,
        top_k=64,
        do_sample=True,
    )
    raw = processor.decode(outputs[0][input_len:], skip_special_tokens=False)
    parsed = split_model_response(raw, option)

    if parsed.thinking:
        print(f"\n[Thinking]\n{parsed.thinking}\n")

    print(f"\n{parsed.content}")


if __name__ == "__main__":
    main()
