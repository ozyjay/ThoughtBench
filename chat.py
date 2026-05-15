"""Interactive multi-turn chat with local thinking-capable models."""

import argparse

from thoughtbench.config import DEFAULT_MODEL_ID, MODEL_CATALOG, get_model_option
from thoughtbench.model import split_model_response
from thoughtbench.model_loading import load_processor_and_model, model_input_device


def load_model(model_id, load_mode=None):
    option = get_model_option(model_id)
    print(f"Loading {option.display_name} ({option.model_id}) ...")
    processor, model, load_info = load_processor_and_model(
        option.model_id,
        load_mode,
        option,
    )
    print(f"Model loaded ({load_info.detail}).\n")
    return processor, model, option


def generate(processor, model, model_option, messages, enable_thinking):
    text = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=enable_thinking and model_option.supports_thinking,
    )
    inputs = processor(text=text, return_tensors="pt").to(model_input_device(model))
    input_len = inputs["input_ids"].shape[-1]

    outputs = model.generate(
        **inputs,
        max_new_tokens=2048,
        temperature=1.0,
        top_p=0.95,
        top_k=64,
        do_sample=True,
    )
    raw = processor.decode(outputs[0][input_len:], skip_special_tokens=False)
    return split_model_response(raw, model_option)


def main():
    model_ids = tuple(option.model_id for option in MODEL_CATALOG)
    parser = argparse.ArgumentParser(description="Chat with a curated local model")
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
        "--load-mode",
        choices=("auto", "bf16"),
        default=None,
        help="Model loading mode. auto uses MPS on Apple Silicon when available.",
    )
    args = parser.parse_args()

    processor, model, model_option = load_model(args.model_id, args.load_mode)

    messages = [{"role": "system", "content": "You are a helpful assistant."}]

    print("Type your message ('/think' toggles thinking mode; Ctrl+C exits).")
    print(f"Thinking mode: {'ON' if args.think else 'OFF'}\n")

    enable_thinking = args.think

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() == "/think":
            enable_thinking = not enable_thinking
            print(f"Thinking mode: {'ON' if enable_thinking else 'OFF'}")
            continue
        if user_input.lower() == "/reset":
            messages = [{"role": "system", "content": "You are a helpful assistant."}]
            print("Conversation reset.")
            continue

        messages.append({"role": "user", "content": user_input})

        parsed = generate(processor, model, model_option, messages, enable_thinking)

        # Display thinking if present
        if parsed.thinking:
            print(f"\n[Thinking]\n{parsed.thinking}\n")

        response_text = parsed.content
        print(f"\n{model_option.display_name}: {response_text}\n")

        # Store only the final response in history (strip thinking per best practices)
        messages.append({"role": "assistant", "content": response_text})


if __name__ == "__main__":
    main()
