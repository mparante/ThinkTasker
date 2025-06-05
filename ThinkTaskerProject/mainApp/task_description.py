# from huggingface_hub import snapshot_download

# snapshot_download(
#     repo_id="meta-llama/Llama-3.1-8B-Instruct",
#     local_dir="Llama-3.1-8B-Instruct",
#     use_auth_token=True
# )
# This script generate task descriptions from email content using a pre-trained LLM model.
# This script is called at sync_emails_view

from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import torch

base_model_path = "C:/Users/Server/Desktop/ThinkTasker/ThinkTaskerProject/Llama-3.1-8B-Instruct"
adapter_path = "C:/Users/Server/Desktop/ThinkTasker/ThinkTaskerProject/Llama-3.1-8B-Instruct/autotrain-7wi99-5xtz5"

tokenizer = AutoTokenizer.from_pretrained(base_model_path)
base_model = AutoModelForCausalLM.from_pretrained(
    base_model_path,
    device_map="auto",
    torch_dtype=torch.float16
)
model = PeftModel.from_pretrained(base_model, adapter_path)

def extract_task_from_email(email_body):
    messages = [
        {"role": "system", "content": "You are a helpful assistant that summarizes email content in one sentence."},
        {"role": "user", "content": f"{email_body}"}
    ]

    chat_prompt = tokenizer.apply_chat_template(
        conversation=messages,
        tokenize=False,
        add_generation_prompt=True
    )
    tokens = tokenizer(chat_prompt, return_tensors='pt')
    tokens = {k: v.to(model.device) for k, v in tokens.items()}

    with torch.no_grad():
        output_ids = model.generate(
            input_ids=tokens["input_ids"],
            attention_mask=tokens["attention_mask"],
            max_new_tokens=50,
            pad_token_id=tokenizer.eos_token_id
        )

    response = tokenizer.decode(output_ids[0][tokens["input_ids"].shape[1]:], skip_special_tokens=True)
    return response.strip()

# if __name__ == "__main__":
#     email = (
#         "Hi KC, I hope you are doing well. I wanted to remind you about the meeting scheduled for tomorrow at 10 AM. "
#     )
#     task = extract_task_from_email(email)
#     print("Extracted task:", task)