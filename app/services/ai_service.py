import json
import re
from typing import List, Optional

from app.config import settings
from app.schemas import ProductItem


async def extract_products_from_text(text: str) -> List[ProductItem]:
    provider = settings.ai_provider

    if provider == "ollama":
        return await _extract_with_ollama(text)
    elif provider == "openai":
        return await _extract_with_openai(text)
    elif provider == "anthropic":
        return await _extract_with_anthropic(text)

    return _extract_local(text)


# ====== مجاني تماماً: استخراج بالقواعد (بدون أي API) ======
def _extract_local(text: str) -> List[ProductItem]:
    products = []
    lines = text.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line or len(line) < 3:
            continue
        if re.match(r'^[\-•*#\d\.]+', line):
            line = re.sub(r'^[\-•*#\d\.\s]+', '', line).strip()

        item = _parse_line(line)
        if item:
            products.append(item)

    return products


_LINE_PATTERNS = [
    # رقم + اسم + سعر: "1- تيشيرت - 150"
    (r'^\d+\s*[-.)]\s*(.+?)\s*[-–—]\s*(\d+(?:[.,]\d+)?)\s*$', 'name_price'),
    # اسم - سعر - وصف: "تيشيرت - 150 - قطن"
    (r'^(.+?)\s*[-–—]\s*(\d+(?:[.,]\d+)?)\s*[-–—]\s*(.+)$', 'full'),
    # اسم - سعر: "تيشيرت - 150"
    (r'^(.+?)\s*[-–—]\s*(\d+(?:[.,]\d+)?)\s*$', 'name_price'),
    # اسم : سعر: "تيشيرت: 150"
    (r'^(.+?)\s*[:：]\s*(\d+(?:[.,]\d+)?)\s*$', 'name_price'),
    # سعر بعد الاسم: "تيشيرت قطن 150" أو "بنطلون جينز 350"
    (r'^(.+?)\s+(\d{3,}(?:[.,]\d+)?)\s*(?:جنية|جنيه|ج\.م|LE|EGP|ريال|دولار)?\s*$', 'name_price'),
]


def _parse_line(line: str) -> Optional[ProductItem]:
    for pattern, mode in _LINE_PATTERNS:
        m = re.match(pattern, line.strip())
        if m:
            if mode == 'full':
                name = m.group(1).strip()
                price = _parse_price(m.group(2))
                desc = m.group(3).strip()
                return ProductItem(name=name, price=price, description=desc)
            elif mode == 'name_price':
                name = m.group(1).strip()
                price = _parse_price(m.group(2))
                return ProductItem(name=name, price=price)
            else:
                name = m.group(1).strip()
                price = _parse_price(m.group(2))
                return ProductItem(name=name, price=price)

    numbers = re.findall(r'(\d{3,}(?:[.,]\d+)?)', line)
    if numbers and not re.match(r'^\d+$', line.split()[0] if line.split() else ''):
        price = _parse_price(numbers[-1])
        name = re.sub(r'\s*\d{3,}(?:[.,]\d+)?\s*(?:جنية|جنيه|ج\.م|LE|EGP)?\s*$', '', line).strip()
        if name:
            return ProductItem(name=name, price=price)

    return ProductItem(name=line, price=None)


def _parse_price(s: str) -> Optional[float]:
    s = s.replace(',', '').strip()
    try:
        return float(s)
    except ValueError:
        return None


# ====== Ollama (مجاني، محلي) ======
async def _extract_with_ollama(text: str) -> List[ProductItem]:
    import httpx

    prompt = EXTRACTION_PROMPT + text
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{settings.ollama_base_url}/api/generate", json=payload)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("response", "[]")

    return _parse_ai_response(content)


# ====== OpenAI API (مدفوع) ======
async def _extract_with_openai(text: str) -> List[ProductItem]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.ai_model or "gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You extract product data from text and return JSON arrays."},
            {"role": "user", "content": EXTRACTION_PROMPT + text},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "[]"
    return _parse_ai_response(content)


# ====== Anthropic API (مدفوع) ======
async def _extract_with_anthropic(text: str) -> List[ProductItem]:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=settings.ai_model or "claude-3-haiku-20240307",
        max_tokens=4096,
        system="You extract product data from text and return JSON arrays. Return ONLY valid JSON.",
        messages=[{"role": "user", "content": EXTRACTION_PROMPT + text}],
    )
    content = response.content[0].text if response.content else "[]"
    return _parse_ai_response(content)


EXTRACTION_PROMPT = """Extract product information from the text below.
Return a JSON object with a "products" key containing an array of items.
Each item has: name (string), price (number or null), description (string or null).

Rules:
- Extract product names clearly
- Price should be a number (remove currency symbols like جنيه, LE, $, etc.)
- Description should be concise
- If no clear products, return {"products": []}
- Return ONLY valid JSON

Text:
"""


def _parse_ai_response(content: str) -> List[ProductItem]:
    try:
        data = json.loads(content)
        items = data if isinstance(data, list) else data.get("products", data.get("items", []))
        return [ProductItem(**item) for item in items]
    except (json.JSONDecodeError, TypeError):
        return []
