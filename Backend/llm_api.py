import os
from dotenv import load_dotenv
from google import genai

# ====== 1. 初始化配置 ======

# 加载 .env 文件
load_dotenv()

# 读取 API Key
API_KEY = os.getenv("GOOGLE_API_KEY")

# 检查 Key 是否存在
if not API_KEY:
    raise ValueError("❌ 未找到 GOOGLE_API_KEY，请检查 Backend/.env 文件！")

# 初始化客户端
client = genai.Client(api_key=API_KEY)

# ✅ 这里填你测试成功的那个模型名字！
# (不管是 "gemini-2.5-flash" 还是 "gemini-2.0-flash-lite-preview-02-05"，只要能跑就行)
DEFAULT_MODEL = "gemini-2.5-flash" 

# ====== 2. 通用 LLM 调用函数 ======
def call_llm(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """
    调用 Google Gemini 生成文本
    """
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={
                "temperature": 0.3, # 数值越低，回答越严谨
                "max_output_tokens": 8192
            }
        )
        
        if response.text:
            return response.text.strip()
        else:
            return "⚠️ 模型返回了空内容"

    except Exception as e:
        print(f"❌ LLM 调用报错: {e}")
        return f"[LLM Error] {e}"

# ====== 3. RAG 专用函数 (你的报告生成会用到这个) ======
def call_llm_rag(query: str, context: str, model: str = DEFAULT_MODEL) -> str:
    """
    RAG 调用封装：自动把 context (背景数据) 和 query (用户问题) 拼在一起
    """
    prompt = f"""
你是一名专业的 TBM (隧道掘进机) 施工数据分析师。
请根据以下【监测数据】撰写分析报告。

【监测数据背景】
{context}

【分析任务】
{query}

要求：
1. 语言专业、客观，使用工程术语。
2. 如果数据中有异常（如停机时间长、气体超标），请重点指出。
3. 不要编造数据，严格基于提供的背景信息。
"""
    return call_llm(prompt, model=model)