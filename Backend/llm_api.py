# llm_api.py
import google.genai as genai
import os
#API_KEY="AIzaSyD_JikQ0R9JkSp6JjPu2T8kuzJMTe_0Uos"
API_KEY="AIzaSyBJTLvwJx3aBDvexPSX1PUMvWuayeNDOhc"
client = genai.Client(api_key=API_KEY)

# 默认使用的模型（你可以换成 gemini-2.5-flash、gemini-2.5-pro）
DEFAULT_MODEL = "gemini-2.5-flash-lite" 

# ====== 2. 通用 LLM 调用函数 ======
def call_llm(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """
    调用 Google Gemini 的文本生成接口，返回模型纯文本。
    prompt: 你的构造的完整 prompt
    model: 默认使用 gemini-2.5-flash
    """
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={
                "temperature": 0.3,  # 保持稳定输出
                "max_output_tokens": 8192
            }
        )

        # 返回主消息
        # Gemini 默认结构是：response.text
        return response.text.strip()

    except Exception as e:
        return f"[LLM Error] {e}"


# ====== 3. 用于 RAG 的 LLM（可选扩展） ======
def call_llm_rag(query: str, context: str, model: str = DEFAULT_MODEL) -> str:
    """
    用于 RAG 的调用封装 —— 给定 context + 用户 query
    """
    prompt = f"""
以下是与问题相关的背景信息：

【检索到的内容】
{context}

【用户问题】
{query}

请基于上述内容回答问题，不得编造额外信息。
"""
    return call_llm(prompt, model=model)
