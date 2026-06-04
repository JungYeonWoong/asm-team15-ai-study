# .env.example에 있는 API 키 활용 방법

```python
# pip install openai
 
from openai import OpenAI # openai==1.52.2
 
client = OpenAI(
    api_key="up_oocywAzvPEM4tVDJydtvLMN6bTo9f",
    base_url="https://api.upstage.ai/v1"
)
 
stream = client.chat.completions.create(
    model="solar-pro3",
    messages=[
        {
            "role": "user",
            "content": "Hi, how are you?"
        }
    ],
    stream=True,
)
 
for chunk in stream:
    if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="")
 
# Use with stream=False
# print(stream.choices[0].message.content)
```
