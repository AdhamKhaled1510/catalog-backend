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
    elif provider == "gemini":
        return await _extract_with_gemini(text)

    return _extract_local(text)


# ====== مجاني تماماً: استخراج بالقواعد (بدون أي API) ======
_GREETINGS_PATTERN = re.compile(
    r'^(السلام عليكم|وعليكم السلام|سلام|مرحبا|اهلا|مرحباً|تحية طيبة|بسم الله|يا باشا|يا كبير|يا عم|يا اخي|يا أخ)\s*',
    re.IGNORECASE,
)


def _extract_local(text: str) -> List[ProductItem]:
    text = text.strip()
    for _ in range(10):
        new_text = _GREETINGS_PATTERN.sub('', text).strip()
        if new_text == text:
            break
        text = new_text

    products = []

    lines = text.split("\n")

    # If all in one line (no line breaks) — try to split by numbered items
    if len(lines) == 1:
        products = _extract_from_one_line(text)
    else:
        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue
            line = re.sub(r'^[\-•*#\d\.\s]+', '', line).strip()
            item = _parse_line(line)
            if item:
                products.append(item)

    return products


_WORDS_TO_SKIP = re.compile(
    r'^(عندي|عندنا|عندك|متوفر|متاح|يوجد|في|ومتوفر|وايضاً|أيضا|كمان|برضو|حد عندك|عند|معانا|موجود|ودي|ودا|دي|تشكيلة|مجموعة|مجموعات|جديد|الشتاء|الصيف|الربيع|الخريف|الجديد|الجديدة|أجمل|أحدث|أفضل|شتاء|صيف|ربيع|خريف|شتوي|صيفي)\s+',
    re.IGNORECASE,
)
_NUMBER_PREFIX = re.compile(r'^\d+\s*[-.)]\s*')
_DASH_SUFFIX = re.compile(r'\s*[-–—]+\s*$')

def _clean_product_name(name: str) -> str:
    name = _NUMBER_PREFIX.sub('', name).strip()
    name = _DASH_SUFFIX.sub('', name).strip()
    # Apply word skipping multiple times
    for _ in range(5):
        new_name = _WORDS_TO_SKIP.sub('', name).strip()
        if new_name == name:
            break
        name = new_name
    name = _NUMBER_PREFIX.sub('', name).strip()
    return name

def _extract_from_one_line(text: str) -> List[ProductItem]:
    # Try: find price-like numbers and pair each with preceding text
    matches = list(re.finditer(r'(.+?)\s*(\d{3,}(?:[.,]\d+)?)\s*(?:جنية|جنيه|ج\.م|LE|EGP|ريال|دولار)?\s*', text))
    if len(matches) > 1:
        result = []
        end = 0
        for i, m in enumerate(matches):
            name = _clean_product_name(m.group(1).strip())
            price = _parse_price(m.group(2))
            if price is not None and len(name) > 1:
                if i > 0 and m.start() > end:
                    continue
                name = _WORDS_TO_SKIP.sub('', name).strip()
                if name:
                    result.append(ProductItem(name=name, price=price))
                end = m.end()
        if result:
            return result

    # Try: split by number prefix: "1- ... 2- ... 3- ..."
    numbered = re.split(r'(?=\d+\s*[-.)]\s*)', text)
    if len(numbered) > 1:
        result = []
        for chunk in numbered:
            chunk = chunk.strip()
            if chunk and len(chunk) > 2:
                item = _parse_line(chunk)
                if item:
                    item.name = _clean_product_name(item.name)
                    result.append(item)
        if result:
            return result

    # Last resort: single product extraction
    item = _parse_line(text)
    if item:
        return [item]

    return []


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


# ====== Google Gemini (مجاني - ما عدا API Key) ======
GEMINI_EXTRACTION_PROMPT = """Extract all products from this text. Return a JSON array.
Each item: {"name": string, "price": number or null, "description": string or null}.

Rules:
- Extract each product separately
- Remove greetings and conversational text
- Price is a number (remove جنيه, LE, $, etc.)
- Description is short if available
- If no products, return []
- ONLY valid JSON, no other text

Text:
"""


async def _extract_with_gemini(text: str) -> List[ProductItem]:
    import google.generativeai as genai

    genai.configure(api_key=settings.google_api_key)
    model = genai.GenerativeModel("gemini-2.0-flash-lite")
    response = await model.generate_content_async(GEMINI_EXTRACTION_PROMPT + text)
    content = response.text.strip()
    content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content)
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
