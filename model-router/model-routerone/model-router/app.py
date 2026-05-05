import os
import httpx
import gradio as gr

API_URL = os.getenv("API_URL", "http://localhost:8000")

async def async_generate(model: str, prompt: str):
    payload = {"model": model, "input": prompt}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{API_URL}/generate", json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        return {"error": str(e)}

# synchronous wrapper for Gradio
def generate(model, prompt):
    import asyncio
    return asyncio.run(async_generate(model, prompt))

with gr.Blocks() as demo:
    gr.Markdown("# ModelRouter — Gradio demo\n\nThis demo calls the `/generate` endpoint of the running ModelRouter API. Set `API_URL` env var to point to a remote deployment.")
    with gr.Row():
        model_sel = gr.Dropdown(["qwen-turbo", "gpt-4", "openai-gpt"], value="qwen-turbo", label="Model")
    txt = gr.Textbox(lines=4, placeholder="Enter input text...", label="Input")
    btn = gr.Button("Generate")
    out = gr.JSON(label="Response")

    btn.click(fn=generate, inputs=[model_sel, txt], outputs=out)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.getenv("PORT", 7860)), share=False)
