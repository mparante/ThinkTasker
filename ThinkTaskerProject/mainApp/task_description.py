# from huggingface_hub import snapshot_download

# snapshot_download(
#     repo_id="meta-llama/Llama-3.1-8B-Instruct",
#     local_dir="Llama-3.1-8B-Instruct",
#     use_auth_token=True
# )
# This script generate task descriptions from email content using a pre-trained LLM model.
# This script is called at sync_emails_view

# from transformers import AutoModelForCausalLM, AutoTokenizer
# from peft import PeftModel
# import torch

# base_model_path = "C:/Users/Server/Desktop/ThinkTasker/ThinkTaskerProject/Llama-3.1-8B-Instruct"
# adapter_path = "C:/Users/Server/Desktop/ThinkTasker/ThinkTaskerProject/Llama-3.1-8B-Instruct/autotrain-7wi99-5xtz5"

# tokenizer = AutoTokenizer.from_pretrained(base_model_path)
# base_model = AutoModelForCausalLM.from_pretrained(
#     base_model_path,
#     device_map="auto",
#     torch_dtype=torch.float16
# )
# model = PeftModel.from_pretrained(base_model, adapter_path)

# def extract_task_from_email(email_body):
#     messages = [
#         {"role": "system", "content": "You are a helpful assistant that summarizes email content in one sentence."},
#         {"role": "user", "content": f"{email_body}"}
#     ]

#     chat_prompt = tokenizer.apply_chat_template(
#         conversation=messages,
#         tokenize=False,
#         add_generation_prompt=True
#     )
#     tokens = tokenizer(chat_prompt, return_tensors='pt')
#     tokens = {k: v.to(model.device) for k, v in tokens.items()}

#     with torch.no_grad():
#         output_ids = model.generate(
#             input_ids=tokens["input_ids"],
#             attention_mask=tokens["attention_mask"],
#             max_new_tokens=50,
#             pad_token_id=tokenizer.eos_token_id
#         )

#     response = tokenizer.decode(output_ids[0][tokens["input_ids"].shape[1]:], skip_special_tokens=True)
#     return response.strip()

# if __name__ == "__main__":
#     email = (
#         "Hi KC, I hope you are doing well. I wanted to remind you about the meeting scheduled for tomorrow at 10 AM. "
#     )
#     task = extract_task_from_email(email)
#     print("Extracted task:", task)

# Use a pipeline as a high-level helper
# from transformers import pipeline

# pipe = pipeline("text-generation", model="kcarante/autotrain-7wi99-5xtz5")
# messages = [
#     {"role": "system", "content": "You are a helpful assistant that summarizes email content in one sentence."},
#     {"role": "user", "content": "Please conduct research on how to setup Linux server for our meeting on Tuesday 6/10. Best regards, TL"}
# ]
# print(pipe(messages))

# # AZURE ML
# import os
# import requests
# from dotenv import load_dotenv

# # Load environment variables from .env
# load_dotenv()

# def extract_task_from_email(email_body):
#     endpoint_uri = os.getenv("AZURE_ML_ENDPOINT_URI")
#     api_key = os.getenv("AZURE_ML_API_KEY")
#     if not endpoint_uri or not api_key:
#         raise ValueError("AZURE_ML_ENDPOINT_URI and AZURE_ML_API_KEY must be set in .env or environment variables.")

#     # Prepare the prompt for the model
#     prompt = (
#         "You are a helpful assistant that summarizes email content in one sentence. "
#         "This is used for a To Do task description. Be concise.\n"
#         f"Email: {email_body}"
#     )

#     # Prepare the payload (modify if your endpoint expects a different schema!)
#     data = {
#         "input_data": {
#             "input_string": prompt
#         }
#     }

#     headers = {
#         "Content-Type": "application/json",
#         "Authorization": f"Bearer {api_key}"  # Try Bearer first, if fails, try just api_key
#     }

#     # Send the POST request
#     response = requests.post(endpoint_uri, headers=headers, json=data)
#     print("Status code:", response.status_code)
#     print("Response text:", response.text[:500])  # Show first 500 chars for debugging

#     # Handle the response
#     if response.status_code == 200:
#         try:
#             result = response.json()
#             # Try typical Azure ML response fields
#             if "output_string" in result:
#                 return result["output_string"].strip()
#             elif "outputs" in result and isinstance(result["outputs"], list):
#                 return result["outputs"][0].strip()
#             else:
#                 print("Unexpected response structure:", result)
#                 return ""
#         except Exception as e:
#             print("JSON decode error:", e)
#             print("Raw response:", response.text)
#             return ""
#     else:
#         print(f"API error {response.status_code}: {response.text}")
#         return ""

# # Example usage
# if __name__ == "__main__":
#     test_email = "Please conduct research on how to set up a Linux server for our meeting on Tuesday 6/10. Best regards, TL."
#     summary = extract_task_from_email(test_email)
#     print("\nExtracted task description:", summary)

import os
from huggingface_hub import InferenceClient
from dotenv import load_dotenv

load_dotenv()

client = InferenceClient(
    api_key=os.environ["HF_TOKEN"],
)

def extract_task_from_email(email_body):
    try:
        completion = client.chat.completions.create(
            model="meta-llama/Meta-Llama-3-8B-Instruct",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that summarizes email content in one sentence. This is used for a To Do task description. Be concise."
                },
                {
                    "role": "user",
                    "content": email_body
                }
            ],
            max_tokens=50,
            temperature=0.3,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error calling Hugging Face API: {e}")
        return email_body

# summary = extract_task_from_email("Please conduct research on how to set up Linux server for our meeting on Tuesday.")
# print(summary)